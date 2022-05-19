# Python Chat
A simple chat application written in Python using TCP Sockets and [urwid](https://urwid.org)

![image](https://media.discordapp.net/attachments/976862121784655933/976862179640893590/Screenshot_20220519_161801.jpg)

## Usage
Clone or download this repository however you like.
```sh
$ git clone https://github.com/ravener/python-chat
```
Make sure Python3 is installed and install urwid:
```sh
$ pip install urwid
```
On a terminal session start the server:
```sh
$ python server.py
```
You can stop the server with `CTRL + C`

Now start the client
```sh
$ python client.py
```
You can type `/quit` or `/q` to exit the client.

## TODO
The project is simple and could work well as a private chat server among some friends but there are a few more changes I'd like to have for it to be more practical:
- [  ] Resuming/Reconnecting
- [  ] Ability to type server address (currently it assumes localhost)
- [  ] Message history (without database, just store like last X messages in memory)
- [  ] Useful Slash Commands
- [  ] Some more code clean up and various little things.
- [  ] Demonstrate creating bots. (You can already do this by leveraging the client connection code from `client.py` but I mean demonstrate it and find some practical uses for it)

Who knows maybe I could eventually turn this into a named project?

# License
Released under [MIT License](LICENSE)

Also credits to [nigiri](https://github.com/sushi-irc/nigiri) from which the client side UI is based off, more specifically from [this gist](https://gist.github.com/MarcelWaldvogel/0226812a2213dc8f67ea4cc361836de1)
