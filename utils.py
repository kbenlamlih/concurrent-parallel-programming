from multiprocessing.managers import BaseManager, ListProxy, AcquirerProxy
from multiprocessing import Lock


class Card:
    def __init__(self, color: str, value: int):
        self.color = color
        self.value = value

    def can_stack(self, other_card):
        # Check if self can be stacked on top of other_card
        return True or (self.value == other_card.value and self.color != other_card.color) \
               or (self.color == other_card.color
                   and (self.value == (other_card.value + 1) or self.value == (other_card.value - 1)))

    def __str__(self):
        return f"'{self.color}, {self.value}'"

    def __repr__(self):
        return f"'{self.color}, {self.value}'"

    def __unicode__(self):
        return f"'{self.color}, {self.value}'"


class RemoteManager(BaseManager):
    def __init__(self, address=('',0), authkey=b'', is_server=False):
        self.board = []
        self.pile = []
        self.board_lock = Lock()
        self.pile_lock = Lock()

        self.is_server = is_server

        if self.is_server:
            self.register('get_board', lambda: self.board, ListProxy)
            self.register('get_pile', lambda: self.pile, ListProxy)
            self.register('get_board_lock', lambda: self.board_lock, AcquirerProxy)
            self.register('get_pile_lock', lambda: self.pile_lock, AcquirerProxy)
        else:
            self.register('get_board')
            self.register('get_pile')
            self.register('get_board_lock')
            self.register('get_pile_lock')

        BaseManager.__init__(self, address=address, authkey=authkey)
