#!/usr/bin/env python3
#!/usr/bin/python3
import os
import shutil
import glob
import json
import subprocess
import time
import re
# needs imagemagick, pdftk, cpdf, cairocffi, libffi-dev, python3-pypdf2

# TODO: does not work with nested folder structure
# TODO: copy folder structure from PC to rM
# TODO: make ssh not only config dependent
# TODO: take care of notebooks created in folders
# TODO: check if files/folders with spaces are processed properly
# TODO: check if annotation pdf has also corresponding original, otherwise we may want to upload it

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
        self.hash_folder_structure = None
        self.folder_hash_structure = None
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
        self.sync_files_list        = glob.glob(os.path.join(self.sync_directory,"**", "*.pdf"), recursive=True)
        self.rm_backup_pdf_list     = glob.glob(os.path.join(self.remarkable_backup_directory
                                                    , self.remarkable_content, "*.pdf"))
        self.rm_backup_lines_list   = glob.glob(os.path.join(self.remarkable_backup_directory
                                                    , self.remarkable_content, "*.lines"))


        self.path_visible_names = dict()
        for x in (subprocess
                                    .check_output("ssh remarkable grep visibleName {}/*.metadata"
                                                    .format(self.remarkable_directory)
                                                  , shell=True)
                                    .decode('utf-8')
                                    .replace('"visibleName":',"")
                                    .split("\n")):
            
            z = x.split(":")
            if z[0]!='':
                self.path_visible_names[z[0]] = z[1].strip()[1:-1]
        
        #self.rm_visible_names = [ x.strip()[1:-1] for x in self.rm_visible_names ]
        #self.rm_visible_names = [self.get_metadata(x,"pdf")[1]['visibleName']+".pdf" for x in self.rm_backup_pdf_list]
        # notesList=[ os.path.basename(f) for f in self.rm_backup_lines_list ] # in the loop we remove all that have an associated pdf

    def get_metadata_ssh(self, file_hash):
        return json.loads((subprocess
                                    .check_output("ssh remarkable cat {}"
                                                    .format(file_hash)
                                                  , shell=True)
                                    .decode('utf-8')
                    ))

    def get_folder_hash(self, folder, force=False):
        if not self.folder_hash_structure or force:
            self.get_rm_folder_structure()
        mhash = ""
        if folder in self.folder_hash_structure.keys():
            mhash = self.folder_hash_structure[folder]
        return mhash
    
    def upload(self):
        # We dont want to re-upload Notes
        self.sync_files_list = [ x for x in self.sync_files_list if not "/notes/" in x ]
        
        sync_names = [ os.path.basename(f) for f in self.sync_files_list ]
        sync_names = dict()
        for f in self.sync_files_list:
            base = os.path.basename(f)
            # We dont want to re-upload_annotated pdfs
            if "annot.pdf" != base[-9:]:
                abs_path = "/".join(f.split("/")[:-1])
                # we take whole absolute path not the last folder, in case some 
                # folders in differnt location had the same name
                sync_names[base] = [abs_path, self.get_folder_hash(abs_path)]
        print("")
        print('sync_names', sync_names)
        print("")
        print("self.path_visible_names",self.path_visible_names)
        print("")
        # sync_names = [ x for x in sync_names.keys() if not "annot" in x ]
        #
        # sync_names = dict{file_name: [local_abs_path, rm_parent_hash]}
        # path_visible_names = dict{path_to_metadata_on_rm: file_name}
        # 
        # now check if a given file should not be omited
        upload_dict = dict()
        for file_name, file_path_and_hash in sync_names.items():
            paths = []
            found_visible_name = False
            # for given file_name, check get all possible metadata files
            # all because there can be files with the same names in 
            # different folders
            for hash_path_rm, visible_name in self.path_visible_names.items():
                if file_name == visible_name:
                    # paths on rm to metadata
                    paths.append(hash_path_rm)
                    found_visible_name = True
            # if there was no file on rm, add it to upload dict
            if not found_visible_name:
                upload_dict[file_name] = file_path_and_hash
                print(file_name,file_path_and_hash)
            else:
                # check if any of the relative paths on rm corresponds to folder on host
                # if not it means that the file is in different folder, so it should be
                # uploaded
                for p in paths:
                    metadata = self.get_metadata_ssh(p)
                    if metadata['parent']!=file_path_and_hash[1]:                        
                        upload_dict[file_name] = file_path_and_hash
                        print(file_name,file_path_and_hash)
                    else:
                        print('has parent', metadata, file_path_and_hash)
        
        print("")
        print('upload_dict' , upload_dict)
        print("")
        print('hash_folder_structure',self.hash_folder_structure)
        num_metadata_files_cmd = 'ssh remarkable "ls /home/root/.local/share/remarkable/xochitl/*.metadata | wc -l"'
        num_metadata_files = int(subprocess.check_output(num_metadata_files_cmd, shell=True).decode('utf-8'))
        i = 1
        for file_name, file_path_and_hash in upload_dict.items():
            file_name = file_name if file_name[-4:0]!="pdf" else file_name[:-4]
            parent_fld = file_path_and_hash[0][len(self.sync_directory)+1:]
            file_path = os.path.join(file_path_and_hash[0], file_name)
            print("file path and hash",file_path_and_hash)
            print("parent folder", parent_fld)
            #print(file_path_and_hash[len(self.sync_directory):])
            #print(file_path_and_hash[:-len(file_name)])
            #print(file_path_and_hash[len(self.sync_directory)+1:-1-len(file_name)])
            
            sed_parent = sync_names[file_name][1]
            print("file_name:", file_name)
            
        # ToDo
        # http://remarkablewiki.com/index.php?title=Methods_of_access
            
            mlog(" upload {} from {}".format(file_name, file_path))
            upload_cmd = "".join(["curl 'http://10.11.99.1/upload' -H 'Origin: http://10.11.99.1' -H 'Accept: */*' -H 'Referer: http://10.11.99.1/' -H 'Connection: keep-alive' -F 'file=@", file_path, ";filename=", file_name,";type=application/pdf'"])            
            subprocess.Popen(upload_cmd, shell=True).wait()
            #
            # wait for new metadata file to be created
            #
            num_metadata_files2 = 0
            while num_metadata_files+i != num_metadata_files2:
                num_metadata_files2 = int(subprocess.check_output(num_metadata_files_cmd, shell=True).decode('utf-8'))
                time.sleep(1)
            i = i+1
            cmd = 'ssh remarkable "ls -t {}/*.metadata | head -n 1 | xargs grep -H visibleName"'.format(self.remarkable_directory)    

            #cmd = 'ssh remarkable "grep -r {} {}/" '.format(file_name, self.remarkable_directory) 
            print("")
            print(cmd)
            print("")
            #| xargs ssh remarkable cat    
            last_file_hash = (subprocess
                .check_output(cmd, shell=True)
                .decode('utf-8'))
            print(last_file_hash)
            last_file = last_file_hash.split(":")[-1].strip()[1:-1]
            print(last_file, file_name)
            if last_file == file_name:
                #print((subprocess.check_output("ssh remarkable cat {}".format(last_file), shell=True).decode('utf-8')))
                #print("sed parent, last file", sed_parent, last_file)
                cmd = """
                        ssh remarkable 'sed -i '"'"'s/"parent": ""/"parent": "{}"/g'"'"' {}' && \
                        ssh remarkable 'sed -i '"'"'s/"metadatamodified": false,/"metadatamodified": true,/g'"'"' {}'
                    """.format(sed_parent, last_file_hash.split(":")[0], last_file_hash.split(":")[0])            
                print(cmd)
                subprocess.Popen(cmd, shell=True).wait()
                #print((subprocess.check_output("ssh remarkable cat {}".format(last_file), shell=True).decode('utf-8')))
                if sed_parent != "":
                    mlog("File moved to the correct folder")

    def get_metadata(self, file_name, file_type = "pdf"):
        type_ln = len(file_type)+1
        ref_nr_path = file_name[:-type_ln]
        meta = json.loads(open(ref_nr_path+".metadata").read())
        return ref_nr_path, meta

    def annotated(self):
        # #Later ToDo: find standalone notes files and put those somewhere seperate
        for i in range(0,len(self.rm_backup_lines_list)):
            # Get path and metadata
            ref_nr_path, meta = self.get_metadata(self.rm_backup_lines_list[i], "lines")

            # Make record of pdf files already on device
            # pdf_names_on_rm.append(meta["visibleName"]+".pdf")
            # Do we need to Copy this file from the rM to the computer?
            AnnotPDF = True if ref_nr_path + ".pdf" in self.rm_backup_pdf_list else False

            if AnnotPDF:
                mlog('dealing with annotated pdfs')
                # deal with annotated pdfs                
                dest_path = self.sync_directory
                # Check if a pdf should be in a nested folder
                # If yes, make the annotation there
                if meta['parent']:
                    dest_path = self.hash_folder_structure[meta['parent']]
                
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

                    # Stamp extracted lines onto original with pdftk
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
        
        for i in range(0, len(self.rm_backup_pdf_list)):
            ref_nr_path = self.rm_backup_pdf_list[i][:-4]
            # get meta Data
            meta = json.loads(open(ref_nr_path+".metadata").read())
            # Make record of pdf files already on device
            rm_pdf_name = meta["visibleName"]+".pdf" if meta["visibleName"][-4:]!=".pdf" else meta["visibleName"]
            self.pdf_names_on_rm.append(rm_pdf_name)
    
    def get_rm_folder_structure(self):
        #
        # folder_hash_structure - has absolute local path of a folder and corresponding rm folder hash
        #
        cmd = "ssh remarkable grep -rnHl CollectionType {}/*.metadata".format(self.remarkable_directory)        
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
        
        # check the whole path not only the last folder
        # as some folders may have the same name although
        # begin in different location
        existing_folders = dict()
        i = 0
        sanity_stop = 100
        while structure_metadata and i<sanity_stop:
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
        self.hash_folder_structure = existing_folders
        self.folder_hash_structure = dict()
        for k,v in existing_folders.items():
            self.folder_hash_structure[v] = k

        print("folder_hash_structure", self.folder_hash_structure)
        return existing_folders
    
    def clean(self):
        mlog("Deleting temporary folder")
        shutil.rmtree(self.temp_directory)
    
    def restart(self):
        cmd = "ssh remarkable systemctl restart xochitl"
        mlog("Restarting reMarkable")
        subprocess.Popen(cmd, shell=True).wait()
        mlog("")


    def check_dir_rm(self, abs_local_path):
        print('check_dir_rm',abs_local_path)
        if not self.folder_hash_structure:
            print('getting structure')
            self.get_rm_folder_structure()
        
        if abs_local_path in self.folder_hash_structure.keys():
            print('folder exists')
            return True        
        return False
    
    def create_dir_if_missing_rm(self, abs_local_path, parent_hash=''):
        # A bit of recursion here, if we have nested folders that do not
        # exist on rM. Take the innter one and go through the same proces.
        # If we reach a folder that exists then just pass over the parent_hash.
        if not self.check_dir_rm(abs_local_path):
            print(abs_local_path)
            tmp_path = "/".join(abs_local_path.split('/')[:-1])
            print(tmp_path)
            if self.sync_directory in tmp_path and self.sync_directory != tmp_path:
                time.sleep(1)
                print("create_dir_if_missing_rm | tmp_path :",tmp_path)
                parent_hash = self.create_dir_if_missing_rm(tmp_path, parent_hash)
            else:
                parent_hash = ""
            print("create_dir_if_missing_rm | abs_local_path :",abs_local_path)
            print("parent_hash",parent_hash)
            parent_hash = self.create_dir(abs_local_path, parent_hash)
            
            return parent_hash
        else:
            print("getting hash", abs_local_path,self.folder_hash_structure[abs_local_path])
            return self.folder_hash_structure[abs_local_path].split("/")[-1]
    
    def create_dir(self, abs_local_path, parent_hash=''):
        directory = abs_local_path.split("/")[-1]
        r = re.compile("-(\d+)\.metadata")
        tmp = "00000000-0000-0000-0000-000000000000"
        cmd = 'ssh remarkable "ls -t {}/00000000-0000-0000-0000-*.metadata | sort -r | head -n 1"'.format(self.remarkable_directory)    
        last_manual_folder_hash = subprocess.check_output(cmd, shell=True).decode('utf-8')

        if last_manual_folder_hash != "":
            counter = str(int(r.findall(last_manual_folder_hash)[0])+1)
            manual_folder_hash = last_manual_folder_hash[:-1-len(counter)-len(".metadata")]+counter
        else:
            print("using default")
            manual_folder_hash = os.path.join(self.remarkable_directory, tmp)

        cmd = 'ssh remarkable "echo \'{}\'> {}.content"'.format("{}", manual_folder_hash)
        subprocess.Popen(cmd, shell=True).wait()
        
        metadata = "{"+'''
                            \\"deleted\\": false,
                            \\"lastModified\\": \\"{}\\",
                            \\"metadatamodified\\": true,
                            \\"modified\\": true,
                            \\"parent\\": \\"{}\\",
                            \\"pinned\\": false,
                            \\"synced\\": false,
                            \\"type\\": \\"CollectionType\\",
                            \\"version\\": 0,
                            \\"visibleName\\": \\"{}\\"
                        '''.format(str(int(time.time()*100)), parent_hash, directory)+"}"
        cmd = 'ssh remarkable "echo \'{}\' > {}.metadata"'.format(metadata, manual_folder_hash)
        subprocess.Popen(cmd, shell=True).wait()
        #
        # add the folder to local folder dictionary
        #
        self.folder_hash_structure[abs_local_path] = manual_folder_hash
        self.hash_folder_structure[manual_folder_hash] = abs_local_path
        mlog('rM: Created folder {} | {} | {}'.format(manual_folder_hash, directory,  abs_local_path))
        return manual_folder_hash.split("/")[-1]

def main():
    remarkable = Remarkable(use_ssh = True)
    remarkable.check_dir_structure()
    remarkable.create_dir_if_missing_rm("/home/marcgrab/remarkable/pdfs/test/nested_test")
    remarkable.create_dir_if_missing_rm("/home/marcgrab/remarkable/pdfs/test/nested_test/nested_in_existing/nested_in_existing2")
    remarkable.create_dir_if_missing_rm("/home/marcgrab/remarkable/pdfs/test/nested_test/nested_in_existing/nested_in_existing2/3333")
    sync = input("Do you want to Sync from your rM? (y/n)")
    if sync == "y":
        remarkable.backupRemarkable()
    print(remarkable.get_rm_folder_structure())
    print(remarkable.folder_hash_structure)
    #remarkable.get_file_structure()
    remarkable.get_file_lists()
    remarkable.annotated()
    remarkable.upload()
    remarkable.clean()
    restart = input("You need to restart your rM to get files in right folders.\nDo you want to do it now? (y/n)")
    if restart == "y":
        remarkable.restart()
    
if __name__ == "__main__":
    main()