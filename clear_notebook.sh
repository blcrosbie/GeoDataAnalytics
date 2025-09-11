cd notebooks
find . -name "*.ipynb" -print0 | while read -d $'\0' file
do
    jupyter nbconvert --clear-output --inplace "$file"
done