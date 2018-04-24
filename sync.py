#!/usr/bin/env python3
#!/usr/bin/python3
import os
import shutil
import glob
import json
import subprocess
import time
import re
import random
import inspect
# needs imagemagick, pdftk, cpdf, cairocffi, libffi-dev, python3-pypdf2

# TODO: make ssh not only config dependent
# TODO: take care of notebooks created in folders
# TODO: check if files/folders with spaces are processed properly
# TODO: check if annotation pdf has also corresponding original, otherwise we may want to upload it
# TODO: issue with anntoations, I have examples when annotation made on first page appears on both pages of two page document
#       when notes are taken on two pages, for the same document, everything works fine
# TODO: find standalone notes files and put those somewhere seperate
def mlog(msg):
    curframe = inspect.currentframe()
    calframe = inspect.getouterframes(curframe, 2)
    print(calframe[1][3] + " | " + msg)

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

    def get_file_lists_local(self):
        self.sync_files_list        = glob.glob(os.path.join(self.sync_directory,"**", "*.pdf"), recursive=True)
        mlog("self.sync_files_list: " + str(self.sync_files_list))
        self.rm_backup_pdf_list     = glob.glob(os.path.join(self.remarkable_backup_directory
                                                    , self.remarkable_content, "*.pdf"))
        self.rm_backup_lines_list   = glob.glob(os.path.join(self.remarkable_backup_directory
                                                    , self.remarkable_content, "*.lines"))
        self.abs_file_path_visible_names_rm = dict()
        for x in (subprocess
                    .check_output("ssh remarkable grep visibleName {}/*.metadata"
                                    .format(self.remarkable_directory)
                                    , shell=True)
                    .decode('utf-8')
                    .replace('"visibleName":',"")
                    .split("\n")):
            z = x.split(":")
            if z[0]!='':
                self.abs_file_path_visible_names_rm[z[0]] = z[1].strip()[1:-1]

    def get_file_list_rm(self):
        # get only DocumentType files, no folders
        # self.hash_file_list_rm contains hash and file name
        cmd = 'ssh remarkable "grep -lnr DocumentType /home/root/.local/share/remarkable/xochitl/*.metadata | xargs grep -rn visibleName"'
        hash_file_list = (subprocess
                    .check_output(cmd, shell=True)
                    .decode('utf-8'))                    
        hash_file_list = [x.split(":") for x in hash_file_list.split("\n")]
        hash_file_dict = dict()
        for y in hash_file_list:
            if y[0]!="":
                hash_file_dict[y[0]]=y[-1].strip()[1:-1]

        cmd = 'ssh remarkable "grep -lnr DocumentType /home/root/.local/share/remarkable/xochitl/*.metadata | xargs grep -rn parent"'
        parent_file_list = (subprocess
                    .check_output(cmd, shell=True)
                    .decode('utf-8'))                    
        parent_file_list = [x.split(":") for x in parent_file_list.split("\n")]
        parent_file_dict = dict()
        for y in parent_file_list:
            if y[0]!="":
                parent_file_dict[y[0]]=y[-1].strip()[1:-1]

        parent_hash_file_list = []
        for local_file_name,metadata in parent_file_dict.items():
            parent_hash_file_list.append([local_file_name, hash_file_dict[local_file_name], metadata])
        
        self.parent_hash_file_list = parent_hash_file_list
        
    def get_metadata_ssh(self, folder_hash):
        return json.loads((subprocess
                                    .check_output("ssh remarkable cat {}"
                                                    .format(folder_hash)
                                                  , shell=True)
                                    .decode('utf-8')
                    ))

    def get_folder_hash(self, folder, force=False):
        if not self.folder_hash_structure or force:
            self.get_folder_structure_rm()
        mhash = ""
        if folder in self.folder_hash_structure.keys():
            mhash = self.folder_hash_structure[folder]
        return mhash
    
    def upload(self):
        # We dont want to re-upload Notes
        self.sync_files_list = [ x for x in self.sync_files_list if not "/notes/" in x ]
        print(self.sync_files_list)
        #sync_names = [ os.path.basename(f) for f in self.sync_files_list ]
        sync_names = []
        for f in self.sync_files_list:
            mlog("checking file: " + f)
            base = os.path.basename(f)
            # We dont want to re-upload_annotated pdfs
            if "annot.pdf" != base[-9:]:
                abs_path = "/".join(f.split("/")[:-1])
                # we take whole absolute path not the last folder, in case some 
                # folders in differnt location had the same name
                sync_names.append([base, abs_path, self.get_folder_hash(abs_path)])
                mlog("file added to sync list: " + f)
        mlog("sync_names: " + str(sync_names))
        
        upload_list = []
        for x in sync_names:
            local_file_name, abs_path, folder_hash = x
            paths = []
            found_visible_name = False
            # for given local_file_name, check get all possible metadata files
            # all because there can be files with the same names in 
            # different folders
            for hash_abs_path_rm, visible_name in self.abs_file_path_visible_names_rm.items():
                if local_file_name == visible_name:
                    mlog("there is a file with the same name as {} on rm".format(local_file_name))
                    metadata_rm = self.get_metadata_ssh(hash_abs_path_rm)
                    # if we found file with the same name, let's check if the parent folder
                    # is the current local absolute path
                    if metadata_rm['parent'] != "":
                        if abs_path == self.hash_folder_structure[metadata_rm['parent']]:
                            # paths on rm to metadata
                            #paths.append(hash_abs_path_rm)
                            found_visible_name = True
                            mlog("found_visible_name: "+" | ".join([local_file_name, abs_path, str(found_visible_name)]))
                    else: 
                        if abs_path == self.sync_directory:
                            found_visible_name = True
                            mlog("found_visible_name: "+" | ".join([local_file_name, abs_path, str(found_visible_name)]))

            # if there was no file with the same name on rm, add it to upload dict
            if not found_visible_name:
                upload_list.append([local_file_name, abs_path,folder_hash])
                mlog("added (1): " + " ".join([local_file_name,abs_path, folder_hash]))
            if False:
                # check if any of the relative paths on rm corresponds to folder on host
                # if not it means that the file is in different folder, so it should be
                # uploaded
                no_match = True
                for p in paths:
                    metadata = self.get_metadata_ssh(p)
                    if metadata['parent']==folder_hash:                        
                            no_match = False
                print("no_match: " + str(no_match))
                if no_match:
                    upload_list.append([local_file_name, abs_path, folder_hash])
                    mlog("added (2): " + " ".join([local_file_name,abs_path, folder_hash]))
        
        mlog("upload_list: " + str(upload_list))
        for x in upload_list:
            local_file_name, abs_path, folder_hash = x
            local_file_name = local_file_name if local_file_name[-4:0]!="pdf" else local_file_name[:-4]
            parent_fld = abs_path[len(self.sync_directory)+1:]
            file_path = os.path.join(abs_path, local_file_name)
            mlog("abs_path: " + abs_path)
            mlog("local_file_name: " + local_file_name)
            mlog("folder_hash: " + folder_hash)
            mlog("parent folder: " + parent_fld)

            # if folder_hash is missing and we do not upload to the main 
            # directory, then it means we are missing a folder, and 
            # it should be created
            sed_parent = folder_hash #sync_names[local_file_name][1]
            if folder_hash == "" and abs_path != self.sync_directory:
                sed_parent = self.create_dir_if_missing_rm(abs_path)
            mlog("sed_parent: " + sed_parent)
            
        # ToDo
        # http://remarkablewiki.com/index.php?title=Methods_of_access
            
            mlog("upload {} from {}".format(local_file_name, file_path))
            #
            # first we upload file with random name, and then change it to a proper one
            # but at the same time changing the parent. Otherwise we may overwrite the
            # file in root if we have a file with the same name in one of subfolders
            #
            random_file_hash = "marcin_" + str(random.random())[2:]+".pdf"
            upload_cmd = "".join(["curl 'http://10.11.99.1/upload' -H 'Origin: http://10.11.99.1' -H 'Accept: */*' -H 'Referer: http://10.11.99.1/' -H 'Connection: keep-alive' -F 'file=@", file_path, ";filename=", random_file_hash, ";type=application/pdf'"])            
            subprocess.Popen(upload_cmd, shell=True).wait()

            last_file_hash = ""
            while last_file_hash=="":
                mlog("while | waiting")
                time.sleep(1)
                cmd = 'ssh remarkable "grep -lrn {} {}/*.metadata"'.format(random_file_hash, self.remarkable_directory)
                try:
                    last_file_hash = subprocess.check_output(cmd, shell=True).decode('utf-8')   
                except:
                    pass
                time.sleep(1)
            mlog(cmd)
            mlog(last_file_hash)
            cmd = """
                    ssh remarkable 'sed -i '"'"'s/"parent": ""/"parent": "{}"/g'"'"' {}' && \
                    ssh remarkable 'sed -i '"'"'s/"metadatamodified": false,/"metadatamodified": true,/g'"'"' {}'
                    ssh remarkable 'sed -i '"'"'s/"visibleName": "{}"/"visibleName": "{}"/g'"'"' {}'
                """.format(sed_parent, last_file_hash
                            , last_file_hash
                            , random_file_hash,  local_file_name.replace(".","\."), last_file_hash)            
            mlog(cmd)
            subprocess.Popen(cmd, shell=True).wait()
            if sed_parent != "":
                mlog("File moved to the correct folder")

    def get_metadata(self, local_file_name, file_type = "pdf"):
        type_ln = len(file_type)+1
        ref_nr_path = local_file_name[:-type_ln]
        meta = json.loads(open(ref_nr_path+".metadata").read())
        return ref_nr_path, meta

    def annotated(self):
        #Later ToDo: find standalone notes files and put those somewhere seperate
        for i in range(0,len(self.rm_backup_lines_list)):
            # Get path and metadata
            ref_nr_path, meta = self.get_metadata(self.rm_backup_lines_list[i], "lines")

            # Make record of pdf files already on device
            # pdf_names_on_rm.append(meta["visibleName"]+".pdf")
            # Do we need to Copy this file from the rM to the computer?
            AnnotPDF = True if ref_nr_path + ".pdf" in self.rm_backup_pdf_list else False

            if AnnotPDF:
                mlog("Dealing with annotated pdfs")
                # deal with annotated pdfs                
                dest_path = self.sync_directory
                # Check if a pdf should be in a nested folder
                # If yes, make the annotation there
                # and of course do so if there are any folders on rm
                if meta['parent'] and self.hash_folder_structure:
                    if meta['parent'] in self.hash_folder_structure.keys():
                        dest_path = self.hash_folder_structure[meta['parent']]
                    else:
                        mlog('parent folder {} for {} does not exist in self.hash_folder_strucutre'.format(meta['parent'], meta['visibleName']))
                
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
                    mlog("{} does not exist in the local sync directory".format(meta["visibleName"]))
                    # ToDo allow y/n input whether it should be copied there anyway
            else:
                # deal with blank notes
                # needs imagemagick
                mlog("Exporting Notebook: {}".format(meta["visibleName"]))

                svgOut = os.path.join(self.temp_directory, "note.svg")

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
            try:
                meta = json.loads(open(ref_nr_path+".metadata").read())
                # Make record of pdf files already on device
                rm_pdf_name = meta["visibleName"]+".pdf" if meta["visibleName"][-4:]!=".pdf" else meta["visibleName"]
                self.pdf_names_on_rm.append(rm_pdf_name)
            except FileNotFoundError:
                mlog("file {} does not exist on rm, cannot get metadata, it exists only in backup".format(ref_nr_path))
    
    def get_folder_structure_rm(self):
        #
        # folder_hash_structure - has absolute local path of a folder and corresponding rm folder hash
        #
        cmd = "ssh remarkable 'grep -rnHl CollectionType {}/*.metadata'".format(self.remarkable_directory)        
        try:
            rm_folder_metadata_files = (subprocess
                .check_output(cmd, shell=True)
                .decode('utf-8')
                .split("\n"))
        except subprocess.CalledProcessError:
            mlog("No metafiles for directories found on rM")
            self.hash_folder_structure = dict()
            self.folder_hash_structure = dict()
            return self.folder_hash_structure
        
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
            local_file_name = os.path.basename(f)[:-9]
            structure_metadata[local_file_name] = dict(json.loads(open(f).read()))        
        
        # check the whole path not only the last folder
        # as some folders may have the same name although
        # begin in different location
        existing_folders = dict()
        i = 0
        sanity_stop = 100
        while structure_metadata and i<sanity_stop:
            i += 1
            for local_file_name, metadata in structure_metadata.items():            
                if local_file_name not in existing_folders.keys():
                    fld = metadata['visibleName']
                    parent_fld = None
                    # no parent then use root
                    if not metadata['parent']: 
                        parent_fld = self.sync_directory 
                    else:
                        if metadata['parent'] in existing_folders.keys():
                            parent_fld = existing_folders[metadata['parent']]
                    if parent_fld:
                        new_abs_file_path = os.path.join(parent_fld, fld)
                        create_dir_if_missing(new_abs_file_path)
                        existing_folders[local_file_name] = new_abs_file_path
            for local_file_name in existing_folders.keys():
                if local_file_name in structure_metadata.keys():
                    del structure_metadata[local_file_name]
        self.hash_folder_structure = existing_folders
        self.folder_hash_structure = dict()
        for local_file_name,metadata in existing_folders.items():
            self.folder_hash_structure[metadata] = local_file_name

        mlog("folder_hash_structure: " + str(self.folder_hash_structure))
        return existing_folders
    
    def clean(self):
        mlog("Deleting temporary folder")
        shutil.rmtree(self.temp_directory)
    
    def restart_rm(self):
        cmd = "ssh remarkable systemctl restart xochitl"
        mlog("Restarting reMarkable")
        subprocess.Popen(cmd, shell=True).wait()
    
    def check_dir_rm(self, abs_local_path):
        mlog("abs_local_path: " + abs_local_path)
        if not self.folder_hash_structure:
            mlog("getting rm folder structure")
            self.get_folder_structure_rm()
        
        if abs_local_path in self.folder_hash_structure.keys():
            mlog("folder exists on rm: " + abs_local_path)
            return True        
        return False
    
    def create_dir_if_missing_rm(self, abs_local_path, parent_hash=''):
        # A bit of recursion here, if we have nested folders that do not
        # exist on rM. Take the innter one and go through the same proces.
        # If we reach a folder that exists then just pass over the parent_hash.
        mlog("abs_local_path: " + abs_local_path)        
        if abs_local_path != self.temp_directory:
            if not self.check_dir_rm(abs_local_path):
                tmp_path = "/".join(abs_local_path.split('/')[:-1])
                if self.sync_directory in tmp_path and self.sync_directory != tmp_path:
                    time.sleep(1)
                    mlog("tmp_path: " + tmp_path)
                    parent_hash = self.create_dir_if_missing_rm(tmp_path, parent_hash)
                else:
                    parent_hash = ""
                mlog("parent_hash: " + parent_hash)
                parent_hash = self.create_dir(abs_local_path, parent_hash)
                return parent_hash
            else:
                parent_hash = self.folder_hash_structure[abs_local_path].split("/")[-1]
                mlog("parent_hash: " + parent_hash)
                return parent_hash
    
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
                        '''.format(str(int(time.time()*1000)), parent_hash, directory)+"}"
        cmd = 'ssh remarkable "echo \'{}\' > {}.metadata"'.format(metadata, manual_folder_hash)
        subprocess.Popen(cmd, shell=True).wait()
        #
        # add the folder to local folder dictionary
        # so we do not have to scan metadata files again
        #
        self.folder_hash_structure[abs_local_path] = manual_folder_hash
        self.hash_folder_structure[manual_folder_hash] = abs_local_path
        mlog('rM: Created folder {} | {} | {}'.format(manual_folder_hash, directory,  abs_local_path))
        return manual_folder_hash.split("/")[-1]

def main():
    remarkable = Remarkable(use_ssh = True)
    remarkable.get_file_list_rm()
    remarkable.check_dir_structure()
    sync = input("Do you want to Sync from your rM? (y/n)")
    if sync == "y":
        remarkable.backupRemarkable()
    remarkable.get_folder_structure_rm()
    remarkable.get_file_lists_local()
    remarkable.annotated()
    remarkable.upload()
    remarkable.clean()
    restart_rm = input("You need to restart_rm your rM to get files in right folders.\nDo you want to do it now? (y/n)")
    if restart_rm == "y":
        remarkable.restart_rm()
    
if __name__ == "__main__":
    main()
