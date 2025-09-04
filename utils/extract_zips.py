import os
import zipfile

# Set the base directory to search for zip files
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
print(f"Searching for zip files in: {DATA_DIR}\n")


# Use os.walk() to recursively find all zip files
for root, dirs, files in os.walk(DATA_DIR):
    for file in files:
        if file.endswith('.zip'):
            zip_path = os.path.join(root, file)
            # Create a dedicated extraction path based on the zip file name
            # This ensures the contents are not extracted into the same directory as the zip file
            extract_path = os.path.join(root, os.path.splitext(file)[0])

            # Check if the zip file has already been extracted
            if not os.path.exists(extract_path):
                print(f"Found zip file: {zip_path}")
                print(f"Extracting to: {extract_path}")

                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf_ref:
                        zf_ref.extractall(extract_path)
                    print("Extraction successful.\n")
                except zipfile.BadZipFile:
                    print(f"Error: {zip_path} is not a valid zip file. Skipping.")
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
            else:
                print(f"Skipping {zip_path}, already extracted to {extract_path}.\n")
