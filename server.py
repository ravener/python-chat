import socket
import json
from threading import Thread

ERROR = 0
IDENTIFY = 1
SEND = 2
RECEIVE = 3
JOIN = 4
LEAVE = 5
INFO = 6

class Client:
    def __init__(self, server, socket, address):
        self.server = server
        self.socket = socket
        self.address = address
        self.dead = False
        self.name = None

    def recv(self, size):
        received_chunks = []
        buf_size = 4096
        remaining = size

        while remaining > 0:
            received = self.socket.recv(min(remaining, buf_size))
            if not received:
                print("Not received")
                self.terminate()
                return False

            received_chunks.append(received)
            remaining -= len(received)
            return b"".join(received_chunks)

    def terminate(self):
        if self.dead:
            return

        print("Terminating {}".format(self.address))
        self.dead = True
        self.socket.close()
        
        if self.name is not None:
            self.server.broadcast({
                "op": LEAVE,
                "name": self.name
            }, True)

        if self in self.server.clients:
            self.server.clients.remove(self)

    def handle(self):
        while not self.dead:
            try:
                len_bytes = self.recv(2)
                if not len_bytes:
                    return

                length = int.from_bytes(len_bytes, "big")

                message_bytes = self.recv(length)
                if not message_bytes:
                    return

                message = json.loads(message_bytes.decode("utf8"))
                self.process_message(message)
            except Exception as e:
                print(e)
                self.error("Invalid Payload")

    def error(self, message, terminate=True):
        print("{} error: {}".format(self.address, message))

        if self.dead:
            return False

        try:
            self.send_json({
                "op": ERROR,
                "message": message
            })
        except:
            pass
        finally:
            if terminate:
                self.terminate()

    def send(self, data):
        return self.socket.sendall(data)

    def send_json(self, data):
        dump = json.dumps(data).encode("utf8")
        length = int.to_bytes(len(dump), 2, "big")

        return self.socket.sendall(length + dump)

    def on_send(self, payload):
        if self.name is None:
            return self.error("Must identify first.")

        message = payload.get("message")

        if not message or type(message) is not str:
            return self.error("Missing 'message' field in JSON or is not a string.")

        if len(message) > 2000:
            return self.error("Message too long, must be less than 2000 characters.")

        self.server.send_message(self.name, message)

    def on_identify(self, payload):
        if self.name is not None:
            return self.error("Already identified", False)

        name = payload.get("name")

        if not name or type(name) is not str:
            return self.error("Missing 'name' field in JSON or is not a string.")
        
        if len(name) > 32:
            return self.error("Name cannot be longer than 32 characters.")

        for client in self.server.clients:
            if not client.dead and client.name == name:
                return self.error("Name already in use.", False)

        self.name = name
        print("{} identified as '{}'".format(self.address, self.name))

        self.server.broadcast({
            "op": JOIN,
            "name": self.name
        }, True)

        self.send_json({
            "op": INFO,
            "users": list(map(lambda x: x.name, filter(lambda x: not x.dead and x.name is not None, self.server.clients)))
        })

    def process_message(self, payload):
        op = payload.get("op")

        if not op or type(op) is not int:
            return self.error("Missing 'op' field in JSON or is not an integer")
        
        if op == IDENTIFY: 
            return self.on_identify(payload)
        elif op == SEND:
            return self.on_send(payload)
        else:
            return self.error("Invalid Op Code.")
            

class Server:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", 3000))
        self.sock.listen(5)
        print("Listening on port 3000")
        self.clients = []

    def broadcast(self, message, json=False):
        for client in self.clients:
            # Skip dead clients and ones who didn't identify yet.
            if client.dead or client.name is None:
                continue

            try:
                if json:
                    client.send_json(message)
                else:
                    client.send(message)
            except Exception as e:
                print(e)
                client.terminate()

    def send_message(self, name, message):
        return self.broadcast({
            "op": RECEIVE,
            "user": name,
            "message": message
        }, True)

    def accept(self):
        while True:
            conn, addr = self.sock.accept()
            print("Connection from {}".format(addr))
            client = Client(self, conn, addr)
            self.clients.append(client)

            t = Thread(target=client.handle)
            t.daemon = True
            t.start()

if __name__ == '__main__':
    Server().accept()

