from multiprocessing.managers import BaseManager, ListProxy, AcquirerProxy
from multiprocessing import Lock
from utils import RemoteManager, Card
import sysv_ipc
import pickle
import random
import time
import sys

players = []

end = False

KEY = 5445


if __name__ == '__main__':
    # Init and serves a server-side remote manager
    mgr = RemoteManager(('', 50000), b'abracadabra', True)
    mgr.start()

    # Set-up the game

    pile = mgr.get_pile()
    pileLock = mgr.get_pile_lock()

    # Draw and shuffle cards
    cards = [Card(color, value) for value in range(10) for color in ['RED', 'BLUE']]
    random.shuffle(cards)

    pile.extend(cards)

    card = pile.pop()

    board = mgr.get_board()
    boardLock = mgr.get_board_lock()

    board.append(card)

    # Create messageQueue
    try:
        mq = sysv_ipc.MessageQueue(KEY, sysv_ipc.IPC_CREAT)
    except ExistentialError:
        print("message queue", KEY, ", already exists.")
        sys.exit(1)

    while not end:
        m, t = mq.receive()
        print("Receiving type ", t, "message")
        print("Pile: ", [c for c in pile])
        print("Board: ", [c for c in board])

        if t == 1:
            # Join request
            pid = pickle.loads(m)
            print(pid, ' has requested to join game')

            if len(players) < 4:
                players.append(pid)
                mq.send(b'joined', type=pid)
            else:
                mq.send(b'too many players', type=pid)

            print("Sent")

        if t == 3:
            # No more cards to draw
            for player in players:
                mq.send(pickle.dumps(('end', None)), type=player)

            end = True

        if t == 4:
            # Play
            card, is_last_card, pid = pickle.loads(m)
            print("Player ", pid, "wants to play card ", card)

            # Get last played card
            last_played = board[len(board) - 1]

            pileLock.acquire()

            if card.can_stack(last_played):
                print("Move accepted")

                # Check if a player has won
                if is_last_card:
                    for player in players:
                        # Player PID has won
                        # Send a 'end' message to all players with the PID of the winner
                        mq.send(pickle.dumps(('end', pid)), type=player)
                    end = True
                mq.send(pickle.dumps(('valid', card)), type=pid)
                board.append(card)
                print("Added card to board")
            else:
                mq.send(pickle.dumps(('invalid', card)), type=pid)
                print("Move rejected")

            pileLock.release()

    mq.remove()
    mgr.shutdown()
