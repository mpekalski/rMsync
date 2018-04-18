#!/usr/bin/env python3
#!/usr/bin/python3
import os
import shutil
import glob
import json
import subprocess
# needs imagemagick, pdftk, cpdf, cairocffi, libffi-dev, python3-pypdf2

# TODO: does not work with nested folder structure
def mlog(msg):
    print(msg)

def create_dir_if_missing(directory):
    if not os.path.exists(directory):
        mlog("creating folder: {} ".format(directory))
        os.makedirs(directory)

#https://github.com/reHackable/maxio
#https://github.com/zxdawn/rM2PDF
def git_clone(directory, username, repo):
    if not os.path.exists(os.path.join(directory, repo)):
        mlog("cloning repo: {} ".format(repo))
        git_cmd = "git clone https://github.com/{}/{} {}".format(username
                                                                , repo
                                                                , os.path.join(directory, repo))
        subprocess.Popen(git_cmd, shell=True).wait()

def has_ssh_config():
    ###
    #    Host remarkable
    #          Hostname 10.11.99.1
    #          User root
    #          PreferredAuthentications publickey
    #          IdentityFile /home/${USER}/.ssh/id_rsa
    #          ForwardX11 no
    #          ForwardAgent no
    ###
    try:
        subprocess.check_output('grep -Fx "Host remarkable" ~/.ssh/config', shell=True)
        subprocess.check_output('grep -F  "IdentityFile"    ~/.ssh/config', shell=True)
        return True
    except:
        return False    

class Remarkable:
    def __init__(self, main_directory = None, use_ssh = False, ssh_key_file = None):
        if os.environ["USER"]:
            default_main = "/home/{}/remarkable".format(os.environ["USER"])
        # path to ssh key to authenticate to remarkable
        self.ssh_key_file = ""
        if use_ssh:
            if not has_ssh_config():
                self.ssh_key_file = " -i " + (ssh_key_file or "/home/{}/.ssh/id_rsa".format(os.environ["USER"]))
            else:
                mlog('Using ssh config file')
        
        self.main_directory  = main_directory or default_main
        self.sync_directory  = os.path.join(self.main_directory, "pdfs")
        self.note_directory  = os.path.join(self.sync_directory, "notes")
        self.tools_directory = os.path.join(self.main_directory, "rMTools")
        self.temp_directory  = os.path.join(self.main_directory, "temp")
        self.folder_directory = os.path.join(self.temp_directory, "folder")
        self.remarkable_backup_directory = os.path.join(self.main_directory, "remarkableBackup")
        self.remarkable_content = "xochitl"
        self.remarkable_directory = "/home/root/.local/share/remarkable/xochitl"
        self.remarkable_username = "root"
        self.remarkable_ip = "10.11.99.1"
        self.folder_structure = None
        self.conversion_script_pdf   = os.path.join(self.tools_directory, "maxio/tools/rM2pdf")
        self.conversion_script_notes = os.path.join(self.tools_directory, "maxio/tools/rM2svg")
        self.pdf_names_on_rm = []
        mlog("Main directory:  {}".format(self.main_directory))
        mlog("Sync directory:  {}".format(self.sync_directory))
        mlog("Note directory:  {}".format(self.note_directory))
        mlog("Tools directory: {}".format(self.tools_directory))

    def check_dir_structure(self):
        create_dir_if_missing(self.main_directory)
        create_dir_if_missing(os.path.join(self.main_directory,'rMTools'))
        create_dir_if_missing(self.sync_directory)
        create_dir_if_missing(self.temp_directory)
        create_dir_if_missing(self.note_directory)
        create_dir_if_missing(self.tools_directory)
        create_dir_if_missing(self.folder_directory)
        git_clone(self.tools_directory, "lschwetlick", "maxio")

    def backupRemarkable(self):        
        mlog("Backing up your remarkable files")
        # Sometimes the remarkable doesnt connect properly. In that case turn off & disconnect -> turn on -> reconnect
        backup_cmd = "".join(["scp ", self.ssh_key_file
                                ," -r ", self.remarkable_username
                                ,   "@", self.remarkable_ip
                                ,   ":", self.remarkable_directory
                                ,   " ", self.remarkable_backup_directory
                                ])
        subprocess.Popen(backup_cmd, shell=True).wait()

    def get_file_lists(self):
        self.sync_files_list        = glob.glob(os.path.join(self.sync_directory, "*.pdf"))
        self.rm_backup_pdf_list     = glob.glob(os.path.join(self.remarkable_backup_directory
                                                    , self.remarkable_content, "*.pdf"))
        self.rm_backup_lines_list   = glob.glob(os.path.join(self.remarkable_backup_directory
                                                    , self.remarkable_content, "*.lines"))

        # TODO: make ssh not only config dependent
        self.rm_visible_names = (subprocess
                                    .check_output("ssh remarkable cat {}/*.metadata | grep visibleName"
                                                    .format(self.remarkable_directory)
                                                  , shell=True)
                                    .decode('utf-8')
                                    .replace('"visibleName":',"")
                                    .split("\n"))
        
        self.rm_visible_names = [ x.strip()[1:-1] for x in self.rm_visible_names  ]
        #self.rm_visible_names = [self.get_metadata(x,"pdf")[1]['visibleName']+".pdf" for x in self.rm_backup_pdf_list]
        # notesList=[ os.path.basename(f) for f in self.rm_backup_lines_list ] # in the loop we remove all that have an associated pdf

    def upload(self):
        # we dont want to re-upload Notes
        self.sync_files_list = [ x for x in self.sync_files_list if not "/notes/" in x ]

        sync_names = [ os.path.basename(f) for f in self.sync_files_list ]
        # we dont want to re-upload_annotated pdfs
        sync_names = [ x for x in sync_names if not "annot" in x ]

        upload_list = [x for x in sync_names if not x in self.rm_visible_names]

        for i in range(0,len(upload_list)):
            file_path = glob.glob(os.path.join(self.sync_directory, upload_list[i]))[0]
            file_name = upload_list[i] if upload_list[i][-4:0]!="pdf" else upload_list[:-4]
        # ToDo
        # http://remarkablewiki.com/index.php?title=Methods_of_access
            mlog("upload {} from {}".format(file_name, file_path))
            upload_cmd = "".join(["curl 'http://10.11.99.1/upload' -H 'Origin: http://10.11.99.1' -H 'Accept: */*' -H 'Referer: http://10.11.99.1/' -H 'Connection: keep-alive' -F 'file=@", file_path, ";filename=", file_name,";type=application/pdf'"])
            subprocess.Popen(upload_cmd, shell=True).wait()
    
    def get_metadata(self, file_name, file_type = "pdf"):
        type_ln = len(file_type)+1
        ref_nr_path = file_name[:-type_ln]
        # get metadata
        meta = json.loads(open(ref_nr_path+".metadata").read())
        return ref_nr_path, meta

    def annotated(self):
        # #Later ToDo: find standalone notes files and put those somewhere seperate
        for i in range(0,len(self.rm_backup_lines_list)):
            # get file reference number
            #ref_nr = os.path.basename(self.rm_backup_lines_list[i][:-6])
            #ref_nr_path = self.rm_backup_lines_list[i][:-6]

            # get metadata
            #meta = json.loads(open(ref_nr_path+".metadata").read())
            ref_nr_path, meta = self.get_metadata(self.rm_backup_lines_list[i], "lines")
            # Make record of pdf files already on device
            # pdf_names_on_rm.append(meta["visibleName"]+".pdf")
            # Do we need to Copy this file from the rM to the computer?
            AnnotPDF = True if ref_nr_path + ".pdf" in self.rm_backup_pdf_list else False

            if AnnotPDF:
                mlog('dealing with annotated pdfs')
                # deal with annotated pdfs                
                dest_path = self.sync_directory
                # check if a pdf should be in a nested folder
                # if yes, make the annotation there
                if meta['parent']:
                    dest_path = self.folder_structure[meta['parent']]
                tmp_sync_dir = os.path.join(dest_path, meta["visibleName"])
                sync_file_path = tmp_sync_dir + ".pdf" if meta["visibleName"][-4:]!=".pdf" else tmp_sync_dir
                in_sync_folder = True if glob.glob(sync_file_path)!=[] else False
                if in_sync_folder:
                    original_pdf = glob.glob(sync_file_path)[0]

                    mlog(meta["visibleName"]+" is being exported.")

                    lines_out = os.path.join(dest_path, "lines_temp.pdf")
                    # Could also use empty pdf on remarkable, but computer side annotations are lost. 
                    # This way if something has been annotated lots fo times it may stat to suck in quality
                    # uses github code
                    convertlinesCmd = "".join(["python3 ", self.conversion_script_pdf
                                                         , " -i ", ref_nr_path, ".lines"
                                                         , " -p ", original_pdf
                                                         , " -o ", lines_out])
                    subprocess.Popen(convertlinesCmd, shell=True).wait()

                    # stamp extracted lines onto original with pdftk
                    stamp_cmd = "".join(["pdftk ", original_pdf, " multistamp ", lines_out
                                                               , " output ", original_pdf[:-4], "_annot.pdf"])
                    subprocess.Popen(stamp_cmd, shell=True).wait()
                    # Remove temporary files
                    os.remove(lines_out)
                else:
                    mlog("{} does not exist in the sync directory".format(meta["visibleName"]))
                    # ToDo allow y/n input whether it should be copied there anyway
            else:
                # deal with blank notes
                # needs imagemagick
                mlog("Exporting Notebook {}".format(meta["visibleName"]))

                svgOut   = os.path.join(self.temp_directory, "note.svg")

                mlog("Creating temporary directory")
                #mkdir_cmd = "mkdir " + os.path.join(self.temp_directory , "tmp")
                #subprocess.Popen(mkdir_cmd, shell=True).wait()

                mlog("Converting lines to svg")
                convertlin_svg_cmd = "".join(["python3 ", self.conversion_script_notes
                                                    , " -i ", ref_nr_path, ".lines"
                                                    , " -o ", svgOut])
                subprocess.Popen(convertlin_svg_cmd, shell=True).wait()

                mlog("Converting svgs to pdf")
                convert_svg2pdf_cmd = "".join(["convert -density 100 ", svgOut[:-4],"_*.svg"
                                             , " -transparent white "
                                             , os.path.join(self.note_directory
                                                            , meta["visibleName"].replace(" ", "_")
                                                            )
                                            , ".pdf"
                                            ])
                subprocess.Popen(convert_svg2pdf_cmd, shell=True).wait()

                #mlog("Deleting temporary directory")
                #shutil.rmtree(self.temp_directory, ignore_errors=False, onerror=None)
        
        for i in range(0, len(self.rm_backup_pdf_list)):
            ref_nr_path = self.rm_backup_pdf_list[i][:-4]
            # get meta Data
            meta = json.loads(open(ref_nr_path+".metadata").read())
            # Make record of pdf files already on device
            rm_pdf_name = meta["visibleName"]+".pdf" if meta["visibleName"][-4:]!=".pdf" else meta["visibleName"]
            self.pdf_names_on_rm.append(rm_pdf_name)
    
    def get_rm_folder_structure(self):
        cmd = "ssh remarkable grep -rnHl CollectionType {}/*.metadata".format(self.remarkable_directory)        
            #+ " | ssh remarkable xargs grep visibleName " \
            #+ " | awk {'print$3'}"
        rm_folder_metadata_files = (subprocess
                .check_output(cmd, shell=True)
                .decode('utf-8')
                .split("\n"))
        
        for f in rm_folder_metadata_files:
            if f:
                cmd = "".join(["scp "
                    ," -r ", self.remarkable_username
                    ,   "@", self.remarkable_ip
                    ,   ":", f
                    ,   " ", self.folder_directory
                    ])
                subprocess.Popen(cmd, shell=True).wait()
        
        structure_metadata = dict()
        for f in glob.glob(os.path.join(self.folder_directory, "*.metadata")):
            file_name = os.path.basename(f)[:-9]
            structure_metadata[file_name] = dict(json.loads(open(f).read()))        
        existing_folders = dict()
        i = 0
        while structure_metadata and i<10:
            i += 1
            for k,v in structure_metadata.items():            
                if k not in existing_folders.keys():
                    fld = v['visibleName']
                    parent_fld = None
                    if not v['parent']: 
                        parent_fld = self.sync_directory 
                    else:
                        if v['parent'] in existing_folders.keys():
                            parent_fld = existing_folders[v['parent']]
                    if parent_fld:
                        new_path = os.path.join(parent_fld, fld)
                        create_dir_if_missing(new_path)
                        existing_folders[k] = new_path
            for k in existing_folders.keys():
                if k in structure_metadata.keys():
                    del structure_metadata[k]
        self.folder_structure = existing_folders
        return existing_folders
    
    def clean(self):
        mlog("Deleting temporary folder")
        shutil.rmtree(self.temp_directory) 

def main():
    remarkable = Remarkable(use_ssh = True)
    remarkable.check_dir_structure()
    sync = input("Do you want to Sync from your rM? (y/n)")
    if sync == "y":
        remarkable.backupRemarkable()
    remarkable.get_rm_folder_structure()    
    remarkable.get_file_lists()
    remarkable.annotated()
    remarkable.upload()
    remarkable.clean()
    
if __name__ == "__main__":
    main()