from multiprocessing.managers import BaseManager, ListProxy, AcquirerProxy
from multiprocessing import Lock
from utils import RemoteManager, Card
import sysv_ipc
import os
import pickle
import time
import sys
import threading

players = []

end = False

KEY = 5445

selected_card = 0

# Windows
if os.name == 'nt':
    import msvcrt

    def clear():
        os.system('cls')

# Posix (Linux, OS X)
else:
    import sys
    import termios
    import atexit
    from select import select

    def clear():
        os.system('clear')


class KBHit:

    def __init__(self):
        '''Creates a KBHit object that you can call to do various keyboard things.
        '''

        if os.name == 'nt':
            pass

        else:

            # Save the terminal settings
            self.fd = sys.stdin.fileno()
            self.new_term = termios.tcgetattr(self.fd)
            self.old_term = termios.tcgetattr(self.fd)

            # New terminal setting unbuffered
            self.new_term[3] = (self.new_term[3] & ~termios.ICANON & ~termios.ECHO)
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)

            # Support normal-terminal reset at exit
            atexit.register(self.set_normal_term)

    def set_normal_term(self):
        ''' Resets to normal terminal.  On Windows this is a no-op.
        '''

        if os.name == 'nt':
            pass

        else:
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

    def getch(self):
        ''' Returns a keyboard character after kbhit() has been called.
            Should not be called in the same program as getarrow().
        '''

        s = ''

        if os.name == 'nt':
            return msvcrt.getch().decode('utf-8')

        else:
            return sys.stdin.read(1)

    def getarrow(self):
        ''' Returns an arrow-key code after kbhit() has been called. Codes are
        0 : up
        1 : right
        2 : down
        3 : left
        Should not be called in the same program as getch().
        '''

        if os.name == 'nt':
            msvcrt.getch()  # skip 0xE0
            c = msvcrt.getch()
            vals = [72, 77, 80, 75]

        else:
            c = sys.stdin.read(3)[2]
            vals = [65, 67, 66, 68]

        return vals.index(ord(c.decode('utf-8')))

    def kbhit(self):
        ''' Returns True if keyboard character was hit, False otherwise.
        '''
        if os.name == 'nt':
            return msvcrt.kbhit()

        else:
            dr, dw, de = select([sys.stdin], [], [], 0)
            return dr != []


def display(board, hand):
    """
    Thread displaying the board and the player's hand.
    Refreshes every 0.5s
    :param board:
    :param hand:
    :return:
    """
    global selected_card
    global end

    while not end:
        clear()

        print("Last card on table: ", board[len(board) - 1])

        for pos, card in enumerate(hand):
            # Prints a star to show the selected card
            symbol = '*' if pos == selected_card else ' '
            print(f"[{symbol}]{card}", end='; ')

        print("\n\nQ/D keys to select another card")
        print("S to play selected card")
        print("Esc to exit")

        time.sleep(0.5)


def action(mq, pile, pileLock, hand):
    """
    Thread intercepting keyboard hits to handle them
    :param mq: messageQueue
    :param pile: cards to draw from
    :param pileLock: pile lock
    :param hand: player's hand
    :return: None
    """
    global end
    global selected_card

    kb = KBHit()

    timer_limit = 8
    last = time.time()

    while not end:
        delta = time.time() - last
        if delta > timer_limit:
            # If we took too long to play, we draw a new card
            card = drawCard(pile, pileLock)
            hand.append(card)
            if not card:
                # Handle empty pile event
                mq.send(b'empty', type=3)
                break
            last = time.time()
            print("Too slow")

        if kb.kbhit():
            c = kb.getch()
            if ord(c) == 27 or ord(c) == 4:  # ESC or Ctrl-D
                print("End of game")
                end = True
                break

            elif ord(c) == 115:# S key
                print("Play")
                # Sends the selected card to the server and removes it from our hand
                last = time.time()  # Timer reset
                card = hand[selected_card]
                last_card = len(hand) == 1
                mq.send(pickle.dumps((card, last_card, os.getpid())), type=4)
                del hand[selected_card]

            elif ord(c) == 113: # Q key
                selected_card = (selected_card - 1) % len(hand)

            elif ord(c) == 100: # D key
                selected_card = (selected_card + 1) % len(hand)



def listen(mq, pile, pileLock, hand):
    """
    Listens to server events and handles them
    :param mq: messageQueue
    :param pile: cards pile (to draw from)
    :param pileLock: pile lock
    :param hand: player's hand
    :return: None
    """
    global end

    while not end:
        m, t = mq.receive(type=os.getpid())

        print("Message!")

        message, option = pickle.loads(m)

        if message == 'end':
            if option == os.getpid():
                print("We won")
            else:
                print("We lost")
            end = True
            break

        if message == 'valid':
            print("Good move")

        if message == "invalid":
            print("Bad move")
            hand.append(option)
            # We put back the card in our hand
            card = drawCard(pile, pileLock)
            hand.append(card)
            print("We draw a card")
            if not card:
                mq.send(b'empty', type=3)
                end = True
                break


def drawCard(cards, cardsLock):
    """
    Acquires the lock and draws a card from the pile.
    If there are no more cards in the pile, returns False
    :param cards: pile
    :param cardsLock: pile lock
    :return: Card or False if no card
    """
    cardsLock.acquire()
    if len(cards) > 0:
        drawn = cards.pop()
        cardsLock.release()
        return drawn
    else:
        return False


if __name__ == '__main__':
    # Connecting to remote manager
    mgr = RemoteManager(('', 50000), b'abracadabra')
    mgr.connect()

    pile = mgr.get_pile()
    pileLock = mgr.get_pile_lock()

    board = mgr.get_board()
    boardLock = mgr.get_board_lock()

    # Connecting to messageQueue
    try:
        mq = sysv_ipc.MessageQueue(KEY)
    except ExistentialError:
        print("Can't connect to message queue ", KEY)
        sys.exit(-1)

    pid = os.getpid()

    # Procedure to connect to the server
    mq.send(pickle.dumps(pid), 1)
    print("Listening to ", pid)
    m, t = mq.receive(type=pid)

    if m == b'joined':
        # If the server authorizes us to play, we draw our cards

        hand = [drawCard(pile, pileLock) for _ in range(5)]
        handLock = threading.Lock()

        play_th = threading.Thread(target=display, args=(board, hand))
        action_th = threading.Thread(target=action, args=(mq, pile, pileLock, hand))
        listen_th = threading.Thread(target=listen, args=(mq, pile, pileLock, hand))

        play_th.start()
        action_th.start()
        listen_th.start()

        play_th.join()
        action_th.join()
        listen_th.join()

    elif m == b'too many players':
        # Otherwise, we can't play
        print("Too many players")
        sys.exit(2)
    else:
        print("Server error")
        sys.exit(1)
