import random

import socket

import string

import sys

import time

import os

from watchdog.observers import Observer

from watchdog.events import LoggingEventHandler



CHUNKSIZE = 1_000_000

alocate_id = 100 # Specific ID per user (range: 100-999)

change_list = [] # A list to hold the changes made

already_changes = []



# Generate an ID for a new client

def create_new_id():

    length = 128

    randomstr = ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    return randomstr





# Generate an ID for a new user

def create_new_user_id():

    global alocate_id

    alocate_id = alocate_id + 1

    return alocate_id



# A method to clone a whole folder when a new user is registered

def send_all(id):

    curr_path = os.path.abspath(id)

    # Traverse the directory and all it's sub-directories and files and add commands to create them to the change list

    for rpath, dirs, files in os.walk(id):

        if os.path.abspath(rpath) != curr_path:

            change_list.append(("Created Directory", os.path.relpath(rpath,curr_path)))

            for f in files:

                change_list.append(("Created File", os.path.relpath(os.path.abspath(rpath),curr_path) + os.sep + f))

        else:

            for f in files:

                change_list.append(("Created File", os.path.relpath(os.path.abspath(rpath),curr_path) + os.sep + f))



# A method that receives a change that was made and implements it

def apply_change(client_socket, command, curr_path, id):

    # If a file is involved in the change, intercept it through a loop

    if command == "Created File" or command == "Modified File":

        length = int(client_socket.recv(1024).decode())

        f = open(os.path.abspath(id) + os.sep + curr_path, "wb")

        if length:

            obj = client_socket.recv(1024)

            how_many_recieved = 0

            f.write(obj)

            how_many_recieved += len(obj)

            while length - how_many_recieved > 0:

                obj = client_socket.recv(1024)

                f.write(obj)

                how_many_recieved += len(obj)

        f.close()

        client_socket.send("ACK".encode("utf-8"))

    elif command == "Created Directory":

        os.mkdir(os.path.abspath(id) + os.sep + curr_path)

    elif command == "Deleted File":

        os.remove(os.path.abspath(id) + os.sep + curr_path)

    elif command == "Deleted Directory":

        for root, dirs, files in os.walk(os.path.abspath(id) + os.sep + curr_path, topdown=False):

            for name in files:

                os.remove(os.path.join(root, name))

            for name in dirs:

                os.rmdir(os.path.join(root, name))

        os.rmdir(os.path.abspath(id) + os.sep + curr_path)

    elif command == "Moved":

        both_paths = curr_path.split("#")

        src_path = both_paths[0]

        dest_path = both_paths[1]

        os.rename(os.path.abspath(id) + os.sep + src_path, os.path.abspath(id) + os.sep + dest_path)



# Send all changes that were made

def send_changes(s, change_list, id):

    for t in change_list:

        key = t[0]

        value = t[1]

        s.send(key.encode("UTF-8"))

        s.recv(3) # Expecting ACK

        s.send(value.encode("UTF-8"))

        s.recv(3) # Expecting ACK

        # If the change involves a file that it's contents need to be sent:

        if key == "Created File" or key == "Modified File":

            length = os.path.getsize(os.path.abspath(id) + os.sep + value)

            s.send(str(length).encode("UTF-8"))

            f = open(os.path.abspath(id) + os.sep + value, "rb")

            data = f.read(1024)

            while data:

                s.send(data)

                data = f.read(1024)

            f.close()

            s.recv(3) # Expecting ACK





# Add new changes to other user's lists to wait for them to ask for updates

def notify_changes(client_socket, clients_id_dict, id, user_id):

    client_socket.send(str(len(clients_id_dict[id][user_id])).encode("UTF-8"))

    client_socket.recv(3)  # Expecting ACK



    inner_changes = clients_id_dict[id][user_id]

    for change in inner_changes:

        send_changes(client_socket, change, id)

    clients_id_dict[id][user_id].clear()





# Receives changes that were made and calls 'apply_change' to apply them

def receive_changes(client_socket, clients_id_dict, id, user_id):

    rec_list = []

    key = client_socket.recv(1024).decode()

    while key != "finished":

        client_socket.send("ACK".encode("utf-8")) # Sending ACK

        value = client_socket.recv(1024).decode() # Path

        client_socket.send("ACK".encode("utf-8")) # Sending ACK



        # Remove duplicate 'moved' changes

        if key == "Moved":

            if value not in already_changes:

                already_changes.append(value)

                rec_list.append((key, value))

                apply_change(client_socket, key, value, id)

        else:

            rec_list.append((key, value))

            apply_change(client_socket, key, value, id)

        key = client_socket.recv(1024).decode()



    # Add the changes that were made to each other user with the same ID

    if len(rec_list):

        for user in clients_id_dict[id]:

            if user != user_id:

                clients_id_dict[id][user].append(rec_list)





if __name__ == '__main__':

    dict_of_ids = set() # A set to hold all IDs

    port = int(sys.argv[1])

    clients_id_dict = {} # The main data structure which monitors and stores all changes

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.bind(('', port))

    server.listen(5)

    while True:

        new_id = 0

        new_user_id = 0

        client_socket, client_address = server.accept()

        data = client_socket.recv(131)



        # '@' received indicates that no ID was given, meaning a new client needs to be registered

        if data.decode("utf-8")[:1] == '@':

            new_id = create_new_id()

            print(new_id)

            dict_of_ids.add(new_id)

            client_socket.send(new_id.encode("UTF-8"))

            clients_id_dict[new_id] = {}

            new_user_id = create_new_user_id()

            client_socket.send(str(new_user_id).encode("UTF-8"))

            clients_id_dict[new_id][new_user_id] = []



            # Opens a new directory for the user

            os.mkdir(new_id)

            client_socket.send("ACK".encode("utf-8"))  # Sending ACK

            receive_changes(client_socket, clients_id_dict, new_id, new_user_id)

            client_socket.send("ACK".encode("utf-8"))  # Sending ACK

        else:

            # '@' received indicates that no user ID was given, meaning a new user wants to join an existing client

            new_id = data.decode("utf-8")[:128]

            if data.decode("utf-8")[128:129] == '@':

                new_user_id = create_new_user_id()

                client_socket.send(str(new_user_id).encode("UTF-8"))

                clients_id_dict[new_id][new_user_id] = []



                # Clone the entire directory for the new user

                send_all(new_id)

                send_changes(client_socket, change_list, new_id)

                change_list.clear()

                client_socket.send("finished".encode("utf-8"))

            else:

                new_user_id = int(data.decode("utf-8")[128:131])

        # Receives changes from user

        receive_changes(client_socket, clients_id_dict, new_id, new_user_id)

        # Sends changes that other users made

        notify_changes(client_socket, clients_id_dict, new_id, new_user_id)

        client_socket.send("finished".encode("utf-8"))



        client_socket.close()



        path = sys.argv[0].replace("main.py", "") + new_id