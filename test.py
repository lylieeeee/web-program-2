import os

file_path = "data/users.json"

if os.path.exists(file_path):
    print(f"File exists: {file_path}")
    if os.access(file_path, os.R_OK):
        print("Read access: YES")
    else:
        print("Read access: NO")
else:
    print("File does not exist")
