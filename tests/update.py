import sys
from subprocess import Popen
from time import sleep
import shutil
import os

file_name = sys.argv[0].split('\\')[-1]
print(f'The file name is: {file_name} v0.0.2')

# List of files in the current directory
print(os.listdir())

if 'temp' in file_name:
    print('Im the new version')

else:
    print('Im the old version')
    sleep(2)

    try:
        # Popen('./update_temp')
        Popen(['sleep', '30'])
    except Exception as e:
        print(e)

    sys.exit()

print('done')
input('Press enter to continue')

# file_name_new = 'update'
# file_name_prev = 'update_temp'
#
# try:
#     shutil.move(file_name_prev, file_name_new)  # os.rename(file_name_prev, file_name_new)
# except Exception as e:
#     print(e)
#
# print('done')
