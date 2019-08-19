This scripts are used to configure the initial linking files and databases for the netconf server.

In order to do so, setup_binding.sh needs to be run. The steps to prepare the execution are:

1. Create a file listing the different datastores you want to be created(This datastores have to be yang files)
2. Insert into setup_files directory the pertinent yang files and all the imports they used
3. Create a file listing all the augments of your yang modules
4. Insert the yang files into setup_files directory
5. From setup_files directory, run setup_binding.sh like so:
``
./setup_binding.sh datastores.txt augments.txt
``