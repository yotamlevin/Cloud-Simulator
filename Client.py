import socket

import sys

import time

import os

import logging

from watchdog.observers import Observer

from watchdog.events import LoggingEventHandler



# Folder path

path = sys.argv[3]

change_list = [] # A list to track changes

names = [] # A list to track name changes of files and directories

all_dirs = [] # A list to keep track of all directories in are main folder



# Overiding the Watchdog method that notifies about creation of files and directories

def on_created(event):

    # If the item created isn't a directory:

    if not event.is_directory:

        change_list.append(("Created File", os.path.relpath(event.src_path, path)))

    else:

        if not os.path.relpath(event.src_path, path) in all_dirs:

            change_list.append(("Created Directory", os.path.relpath(event.src_path, path)))

            all_dirs.append(os.path.relpath(event.src_path, path))





# Overiding the Watchdog method that notifies about Deletion of files and directories

def on_deleted(event):

    # If the item deleted isn't a directory:

    if not os.path.relpath(event.src_path, path) in all_dirs:

        change_list.append(("Deleted File", os.path.relpath(event.src_path, path)))

    else:

        change_list.append(("Deleted Directory", os.path.relpath(event.src_path, path)))

        all_dirs.remove(os.path.relpath(event.src_path, path))





# Overiding the Watchdog method that notifies about modification of files and directories

def on_modified(event):

    # If the item modified isn't a directory:

    if not event.is_directory:

        if not ("Modified File", os.path.relpath(event.src_path, path)) in change_list:

            change_list.append(("Modified File", os.path.relpath(event.src_path, path)))





# Overiding the Watchdog method that notifies about movement of files and directories

def on_moved(event):

    change_list.append(("Moved", os.path.relpath(event.src_path, path) + "#" + os.path.relpath(event.dest_path, path)))

    names.append((os.path.relpath(event.src_path, path), os.path.relpath(event.dest_path, path)))





# A method that receives a change that was made and implements it

def apply_change(client_socket, command, curr_path):

    # If a file is involved in the change, intercept it through a loop

    if command == "Created File" or command == "Modified File":

        length = int(client_socket.recv(1024).decode())

        f = open(path + os.sep + curr_path, "wb")

        if length:

            obj = client_socket.recv(1024)

            how_many_received = 0

            f.write(obj)

            how_many_received += len(obj)

            while length - how_many_received > 0:

                obj = client_socket.recv(1024)

                f.write(obj)

                how_many_received += len(obj)

        f.close()

        client_socket.send("ACK".encode("utf-8"))

    elif command == "Created Directory":

        all_dirs.append(curr_path)

        os.mkdir(path + os.sep + curr_path)

    elif command == "Deleted File":

        os.remove(path + os.sep + curr_path)

    elif command == "Deleted Directory":

        all_dirs.remove(curr_path)

        for root, dirs, files in os.walk(path + os.sep + curr_path, topdown=False):

            for name in files:

                os.remove(os.path.join(root, name))

            for name in dirs:

                os.rmdir(os.path.join(root, name))

        os.rmdir(path + os.sep + curr_path)

    elif command == "Moved":

        both_paths = curr_path.split("#")

        src_path = both_paths[0]

        dest_path = both_paths[1]

        os.rename(path + os.sep + src_path, path + os.sep + dest_path)





# Send all changes that were made

def send_changes(s, change_list):

    for t in change_list:

        key = t[0]

        value = t[1]

        s.send(key.encode("UTF-8"))

        s.recv(3) # Expecting ACK

        s.send(value.encode("UTF-8"))

        s.recv(3) # Expecting ACK



        # If the change involves a file that it's contents need to be sent:

        if key == "Created File" or key == "Modified File":

            for name in names:

                if value == name[0]:

                    value = name[1]

            length = os.path.getsize(path + os.sep + value)

            s.send(str(length).encode("UTF-8"))

            f = open(path + os.sep + value, "rb")

            data = f.read(1024)

            while data:

                s.send(data)

                data = f.read(1024)

            f.close()

            s.recv(3) # Expecting ACK





# Receives changes that were made and calls 'apply_change' to apply them

def receive_changes(client_socket):

    key = client_socket.recv(1024).decode()

    while key != "finished":

        client_socket.send("ACK".encode("utf-8")) # Sending ACK

        value = client_socket.recv(1024).decode()  # Path

        client_socket.send("ACK".encode("utf-8")) # Sending ACK

        apply_change(client_socket, key, value)

        key = client_socket.recv(1024).decode()





# A method to clone a whole folder when a new user is registered

def send_all():

    curr_path = path

    # Traverse the directory and all it's sub-directories and files and add commands to create them to the change list

    for rpath, dirs, files in os.walk(curr_path):

        if os.path.abspath(rpath) != curr_path:

            change_list.append(("Created Directory", os.path.relpath(rpath,curr_path)))

            for f in files:

                change_list.append(("Created File", os.path.relpath(os.path.abspath(rpath),curr_path) + os.sep + f))

        else:

            for f in files:

                change_list.append(("Created File", os.path.relpath(os.path.abspath(rpath),curr_path) + os.sep + f))





if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO,

                        format='%(asctime)s - %(message)s',

                        datefmt='%Y-%m-%d %H:%M:%S')



    # Using our implementation of the functions

    event_handler = LoggingEventHandler()

    event_handler.on_created = on_created

    event_handler.on_modified = on_modified

    event_handler.on_deleted = on_deleted

    event_handler.on_moved = on_moved



    # Check if an ID was given

    if len(sys.argv) == 6:

        unique_id = sys.argv[5]

        os.mkdir(path)

    else:

        unique_id = None



    user = None



    # Using Watchdog, check if changes were made to the directory

    observer = Observer()

    observer.schedule(event_handler, os.path.abspath(path), recursive=True)

    observer.start()



    while True:

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        s.connect((sys.argv[1], int(sys.argv[2])))



        # Receive ID and user ID from server, if necessary

        if unique_id:

            if user:

                s.send((unique_id + user).encode("UTF-8"))

            else:

                s.send((unique_id + "@").encode("UTF-8"))

                user = s.recv(3).decode()

                receive_changes(s) # Clone directory

                change_list.clear()

        else:

            s.send("@".encode("UTF-8"))

            unique_id = s.recv(128).decode()

            user = s.recv(3).decode() # Receive User ID

            s.recv(3)  # Expecting ACK

            send_all()

            send_changes(s, change_list)

            change_list.clear()

            s.send("finished".encode("utf-8"))

            s.recv(3)  # Expecting ACK



        # Update the server with new changes

        send_changes(s, change_list)

        names.clear()

        change_list.clear()

        s.send("finished".encode("UTF-8"))



        numOfChanges = int(s.recv(1024).decode())

        s.send("ACK".encode("utf-8"))



        # Apply all changes that other users made

        if numOfChanges:

            for i in range(numOfChanges):

                receive_changes(s)

                change_list.clear()



        s.close()

        time.sleep(int(sys.argv[4]))



    observer.stop()

    observer.join()