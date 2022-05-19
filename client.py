#!/usr/bin/env python3
# coding: UTF-8

# Adapted from https://gist.github.com/MarcelWaldvogel/0226812a2213dc8f67ea4cc361836de1
# code extracted from nigiri
# Got running on current version and Python3

import os
import datetime
import sys
import traceback
import re
import logging
import locale
import socket
import json
from threading import Thread

import urwid
from urwid import MetaSignals

class ExtendedListBox(urwid.ListBox):
    """
        ListBox widget with embeded autoscroll
    """

    __metaclass__ = urwid.MetaSignals
    signals = ["set_auto_scroll"]

    def set_auto_scroll(self, switch):
        if type(switch) != bool:
            return

        self._auto_scroll = switch
        urwid.emit_signal(self, "set_auto_scroll", switch)


    auto_scroll = property(lambda s: s._auto_scroll, set_auto_scroll)


    def __init__(self, body):
        urwid.ListBox.__init__(self, body)
        self.auto_scroll = True


    def switch_body(self, body):
        if self.body:
            urwid.disconnect_signal(body, "modified", self._invalidate)

        self.body = body
        self._invalidate()

        urwid.connect_signal(body, "modified", self._invalidate)


    def keypress(self, size, key):
        urwid.ListBox.keypress(self, size, key)

        if key in ("up", "down", "page up", "page down"):
            logging.debug("focus = %d, len = %d" % (self.get_focus()[1], len(self.body)))
            if self.get_focus()[1] == len(self.body)-1:
                self.auto_scroll = True
            else:
                self.auto_scroll = False
            logging.debug("auto_scroll = %s" % (self.auto_scroll))

    def scroll_to_bottom(self):
        logging.debug("current_focus = %s, len(self.body) = %d" % (self.get_focus()[1], len(self.body)))

        if self.auto_scroll:
            # at bottom -> scroll down
            self.set_focus(len(self.body)-1)

# Socket Op Codes
ERROR = 0
IDENTIFY = 1
SEND = 2
RECEIVE = 3
JOIN = 4
LEAVE = 5
INFO = 6

class SocketClient:
    def __init__(self, window):
        self.window = window

        self.identified = False
        self.online = 0
        self.bytes_sent = 0
        self.bytes_recv = 0

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(("", 3000))

    def start(self):
        self.connect()

        thread = Thread(target=self.handle_message)
        thread.daemon = True
        thread.start()

    def send_json(self, data):
        dump = json.dumps(data).encode("utf8")
        length = int.to_bytes(len(dump), 2, "big")
        
        self.sock.sendall(length + dump)
        self.bytes_sent += len(dump) + 16
        self.update_data()

    def update_data(self):
        sent = self.bytes_sent / 1024
        if sent > 1000:
            sent = "{:.2f} MB".format(sent / 1024)
        else:
            sent = "{:.2f} KB".format(sent)

        recv = self.bytes_recv / 1024
        if recv > 1000:
            recv = "{:.2f} MB".format(recv / 1024)
        else:
            recv = "{:.2f} KB".format(recv)

        self.window.divider.contents[2][0].set_text("↑ {} ↓ {}".format(sent, recv))
        self.window.draw_interface()

    def send_message(self, message):
        return self.send_json({
            "op": SEND,
            "message": message
        })

    def identify(self, name):
        return self.send_json({
            "op": IDENTIFY,
            "name": name
        })
    
    def recv(self, size):
        received_chunks = []
        buf_size = 4096
        remaining = size

        while remaining > 0:
            received = self.sock.recv(min(remaining, buf_size))

            if not received:
                # TODO: Implement reconnecting
                self.window.print_text("Connection lost.")
                self.window.draw_interface()
                return

            received_chunks.append(received)
            remaining -= len(received)

        return b"".join(received_chunks)
    
    def show_online(self):
        self.window.divider.contents[1][0].set_text("{} Users Online".format(self.online))

    def on_receive(self, user, message):
        self.window.print_received_message(user, message)
        self.window.draw_interface()

    def on_join(self, name):
        text = urwid.Text([('bold_text', name), ' has joined the chat'])
        self.window.print_text(text)
        self.online += 1
        self.show_online()
        self.window.draw_interface()

    def on_leave(self, name):
        text = urwid.Text([('bold_text', name), ' has left the chat'])
        self.window.print_text(text)
        self.online -= 1
        self.show_online()
        self.window.draw_interface()

    def on_error(self, message):
        logging.error(message)

        if "Name already in use" in message:
            text = urwid.Text([('bold_text', "Error: "), "Name already in use."])
            self.window.print_text(text)
            self.window.draw_interface()

    def on_info(self, users):
        self.online = len(users)
        self.identified = True
        self.window.divider.contents[0][0].set_text(("divider", "Send message:"))
        self.window.divider.contents[1][0].set_text("{} Users Online".format(len(users)))
        self.window.draw_interface()

    def handle_message(self):
        while True:
            length = int.from_bytes(self.recv(2), "big")
            payload = json.loads(self.recv(length).decode("utf8"))
            self.bytes_recv += length + 16
            self.update_data()

            if payload["op"] == RECEIVE:
                self.on_receive(payload["user"], payload["message"])
            elif payload["op"] == JOIN:
                self.on_join(payload["name"])
            elif payload["op"] == LEAVE:
                self.on_leave(payload["name"])
            elif payload["op"] == ERROR:
                self.on_error(payload["message"])
            elif payload["op"] == INFO:
                self.on_info(payload["users"])
        


"""
 -------context-------
| --inner context---- |
|| HEADER            ||
||                   ||
|| BODY              ||
||                   ||
|| DIVIDER           ||
| ------------------- |
| FOOTER              |
 ---------------------

inner context = context.body
context.body.body = BODY
context.body.header = HEADER
context.body.footer = DIVIDER
context.footer = FOOTER
HEADER = Notice line (urwid.Text)
BODY = Extended ListBox
DIVIDER = Divider with information (urwid.Text)
FOOTER = Input line (Ext. Edit)
"""

class MainWindow(object):

    __metaclass__ = MetaSignals
    signals = ["quit", "keypress"]

    _palette = [
            ('divider','black','dark cyan', 'standout'),
            ('text','light gray', 'default'),
            ('bold_text', 'light gray', 'default', 'bold'),
            ("body", "text"),
            ("footer", "text"),
            ("header", "text"),
        ]

    for type, bg in (
            ("div_fg_", "dark cyan"),
            ("", "default")):
        for name, color in (
                ("red","dark red"),
                ("blue", "dark blue"),
                ("green", "dark green"),
                ("yellow", "yellow"),
                ("magenta", "dark magenta"),
                ("gray", "light gray"),
                ("white", "white"),
                ("black", "black")):
            _palette.append((type + name, color, bg))


    def __init__(self, sender="1234567890"):
        self.shall_quit = False
        self.sender = sender
        self.socket = SocketClient(self)

    def main(self):
        """ 
            Entry point to start UI 
        """

        self.ui = urwid.raw_display.Screen()
        self.ui.register_palette(self._palette)
        self.build_interface()
        self.socket.start()
        self.ui.run_wrapper(self.run)

    def on_recv(self, user, msg):
        self.print_received_message(user, msg)

    def run(self):
        """ 
            Setup input handler, invalidate handler to
            automatically redraw the interface if needed.
            Start mainloop.
        """

        # I don't know what the callbacks are for yet,
        # it's a code taken from the nigiri project
        def input_cb(key):
            if self.shall_quit:
                raise urwid.ExitMainLoop
            self.keypress(self.size, key)

        self.size = self.ui.get_cols_rows()

        self.main_loop = urwid.MainLoop(
                self.context,
                screen=self.ui,
                handle_mouse=False,
                unhandled_input=input_cb,
            )

        def call_redraw(*x):
            self.draw_interface()
            invalidate.locked = False
            return True

        inv = urwid.canvas.CanvasCache.invalidate

        def invalidate(cls, *a, **k):
            inv(*a, **k)

            if not invalidate.locked:
                invalidate.locked = True
                self.main_loop.set_alarm_in(0, call_redraw)

        invalidate.locked = False
        # For some reason this parts cause some issue
        # when I spam a lot of messages and test scrolling
        # urwid.canvas.CanvasCache.invalidate = classmethod(invalidate)

        try:
            self.main_loop.run()
        except KeyboardInterrupt:
            self.quit()

    def quit(self, exit=True):
        """ 
            Stops the ui, exits the application (if exit=True)
        """
        urwid.emit_signal(self, "quit")

        self.shall_quit = True

        if exit:
            sys.exit(0)

    def build_interface(self):
        """ 
            Call the widget methods to build the UI 
        """

        self.header = urwid.Text("Chat")
        self.footer = urwid.Edit("=> ")
        self.divider = urwid.Columns([
            urwid.Text("Initializing."),
            urwid.Text("Not Joined", align="right"),
            urwid.Text("↑ 0 KB ↓ 0 KB", align="right")
        ])

        self.generic_output_walker = urwid.SimpleListWalker([])
        self.body = ExtendedListBox(self.generic_output_walker)

        self.header = urwid.AttrWrap(self.header, "divider")
        self.footer = urwid.AttrWrap(self.footer, "footer")
        self.divider = urwid.AttrWrap(self.divider, "divider")
        self.body = urwid.AttrWrap(self.body, "body")

        self.footer.set_wrap_mode("clip")

        main_frame = urwid.Frame(self.body, 
                                header=self.header,
                                footer=self.divider)
        
        self.context = urwid.Frame(main_frame, footer=self.footer)

        self.divider.contents[0][0].set_text(("divider",
                               ("Enter a username:")))
        
        self.context.set_focus("footer")

    def draw_interface(self):
        self.main_loop.draw_screen()

    def identify(self, name):
        self.socket.identify(name)

    def keypress(self, size, key):
        """ 
            Handle user inputs
        """

        urwid.emit_signal(self, "keypress", size, key)

        # scroll the top panel
        if key in ("up", "down", "page up","page down"):
            self.body.keypress(size, key)

        # resize the main windows
        elif key == "window resize":
            self.size = self.ui.get_cols_rows()

        elif key in ("ctrl d", 'ctrl c'):
            self.quit()

        elif key == "enter":
            # Parse data or (if parse failed)
            # send it to the current world
            text = self.footer.get_edit_text()

            self.footer.set_edit_text(" "*len(text))
            self.footer.set_edit_text("")

            if text in ('/quit', '/q'):
                self.quit()

            if text.strip():
                if not self.socket.identified:
                    self.identify(text)
                else:
                    self.socket.send_message(text)
        else:
            self.context.keypress(size, key)

    def print_received_message(self, user, text):
        """
            Print a sent message
        """

        self.print_text(urwid.Text([
            ('bold_text', user + ': '),
            text
        ]))

    def print_text(self, text):
        """
            Print the given text in the _current_ window
            and scroll to the bottom. 
            You can pass a Text object or a string
        """

        walker = self.generic_output_walker

        if not isinstance(text, urwid.Text):
            text = urwid.Text(text)

        walker.append(text)

        self.body.scroll_to_bottom()

    def get_time(self):
        """
            Return formated current datetime
        """
        return datetime.datetime.now().strftime('%I:%M:%S %p')


def except_hook(extype, exobj, extb, manual=False):
    if not manual:
        try:
            main_window.quit(exit=False)
        except NameError:
            pass

    message = ("An error occured:\n%(divider)s\n%(traceback)s\n"\
        "%(exception)s\n%(divider)s" % {
            "divider": 20*"-",
            "traceback": "".join(traceback.format_tb(extb)),
            "exception": extype.__name__+": "+str(exobj)
        })

    logging.error(message)

    print(message, file=sys.stderr)

def setup_logging():
    """ set the path of the logfile to tekka.logfile config
        value and create it (including path) if needed.
        After that, add a logging handler for exceptions
        which reports exceptions catched by the logger
        to the tekka_excepthook. (DBus uses this)
    """
    try:
        class ExceptionHandler(logging.Handler):
            """ handler for exceptions caught with logging.error.
                dump those exceptions to the exception handler.
            """
            def emit(self, record):
                if record.exc_info:
                    except_hook(*record.exc_info)

        logfile = 'chat.log'
        # logdir = os.path.dirname(logfile)

        # if not os.path.exists(logdir):
        #    os.makedirs(logdir)

        logging.basicConfig(filename=logfile, level=logging.DEBUG,
            filemode="w")

        logging.getLogger("").addHandler(ExceptionHandler())

    except BaseException as e:
        print("Logging init error: %s" % (e), file=sys.stderr)


if __name__ == "__main__":
    setup_logging()
    main_window = MainWindow()
    sys.excepthook = except_hook
    main_window.main()

