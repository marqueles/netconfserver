if [ "$#" -ne "2" ]; then
  	echo "Sorry, you need to include a file with the datastores and another with the augments, aditionally you should ad a folder with the associated yang files(datastores, imports and augments) , called setup_files "
	exit 1
fi
dependencies="$(cat $1)"
dependencies="$dependencies $(cat $2)"
#echo $dependencies

PYBINDPLUGIN=$(/usr/bin/env python -c 'import pyangbind; import os; print ("{}/plugin".format(os.path.dirname(pyangbind.__file__)))')
#echo $PYBINDPLUGIN

#pyang --plugindir $PYBINDPLUGIN -f pybind -o binding.py $dependencies
#cp binding.py ../


cat $1 | while read -r line
do
  python setup_db.py "$line"
done