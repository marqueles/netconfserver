if [ "$#" -ne "3" ]; then
  	echo "You need to include three parameters:\n\r"
  	echo "1) A file with the datastores\n\r"
  	echo "2) A file with the augments\n\r"
  	echo "3) A file with the startup config\n\r"
  	exit 1
fi
dependencies="$(cat $1)"
dependencies="$dependencies $(cat $2)"
config=$3

PYBINDPLUGIN=$(/usr/bin/env python -c 'import pyangbind; import os; print ("{}/plugin".format(os.path.dirname(pyangbind.__file__)))')

cat $1 | while read -r line
do
  newline=${line/.yang/}
  filename="binding_"$newline".py"
  pyang --plugindir $PYBINDPLUGIN -f pybind -o $filename $dependencies
  cp $filename bindings/
  cp $filename ../bindings/
  rm $filename
  python setup_db.py "$newline" "$config"
done
