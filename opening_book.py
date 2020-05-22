#TODO: merge fens that differ only in the 50 move counter, that won't ever matter for openings
#also update PROBABILITY_MULTIPLIERS variable when doing this
#eg
#/ssd/files/chess/filtered_moves.csv | grep rnbqk2r/ppppppbp/5np1/8/2PP4/2N2N2/PP2PPPP/R1BQKB1R

#compute the best opening book given
#given and a maximum number of moves to remember
#computes the most effective positions to memorize
#this works by taking in a list of real game positions
#(at least 20 instances of each position), together with
#the played responses to give a sense for how humans
#play out a position instead of relying entirely
#on stockfish evals

from eval_moves import Evaluator, hash_fen, fen_plus_move, move_history_to_fen
import csv
from jtutils import pairwise
import sys
import chess
import pickle
import math
import collections
import numpy as np
import itertools
import time
import shelve
import os
import random

#read the graph of positions, along with the ev
EVALUATOR = Evaluator()

INPUT_FILE = "/ssd/files/chess/filtered_moves.csv"
EVAL_TIME = 1000

CACHE_STATS = {}

MAX_CACHED_MOVES = 1000 * 30000 #30000 superbooks of size 1000

DISK_CACHE_THRESHOLD = 20 # * 1000000
CACHE_STATS_THRESHOLD = 20 # * 1000000

class SuperbookCache():
    def __init__(self):
        self.cnt = 0
        filename = "/tmp/shelve"
        if os.path.exists(filename):
            os.remove(filename)
        self.shelf = shelve.open(filename)
    def save_cache(self, fen, n, player, superbook):
        if str((fen, n, player)) not in self.shelf:
            self.cnt += 1
        self.shelf[str((fen, n, player))] = superbook
    def load_cache(self, fen, n, player):
        return self.shelf[str((fen, n, player))]
    def evict(self, fen, n, player):
        if str((fen, n, player)) in self.shelf:
            self.cnt -= 1
        del self.shelf[str((fen, n, player))]
    def in_cache(self, fen, n, player):
        return str((fen, n, player)) in self.shelf

disk_cache = SuperbookCache()


LEAF_COUNT = 0

#TODO: add a second, lower CACHE_THRESHOLD that is only triggered after we've encountered
#the position k times (k=2? k=3? probably test to see how the memory vs speed tradeoff is)

INCLUDE_PLACEHOLDERS = True

#PLAYER_STRENGTH variable tries to model opening play stronger than
#the database. default PLAYER_STRENGTH is 1. Higher player strength
#means the players are expected to play the most common move more frequently
#NOTE: this assumes the most common move is the best one, hoping
#it generally is for a good database
PLAYER_STRENGTH = 1

#value of studying k moves out of book
#This was originally based on a rough
#fit of 0.0036 * math.log(move_cnt + 1)
#for learning moves *in book* from the KingBase database.
#then multiplying by a fudge factor of (2 / PLAYER_STRENGTH) #update: temporarily removed
#because moves out of book should be more effective
#and moves against stronger players should be less effective
OUT_OF_BOOK_PREP_VALUE = lambda x: 0.0036 * math.log(x+1)

#adjust the weights of certain moves
PROBABILITY_MULTIPLIERS = {
    #KID is a bad opening according to the internet, also Stockfish.
    #but for some reason 4..O-O is the most popular move here,
    #which makes for a really strong opening book hinging on
    #1. d4  Nf6
    #2. Nf3 g6  (g6 slightly more common than e6 here)
    #3. c4  Bg7
    #4. Nc3 O-O
    #5. e4  d6
    #6. Be2 e5
    #7. O-O Nc6
    #8. d5  Ne7
    #every move other than 2..g6 is easily the most popular for black for some reason?
    #4..O-O seems like where this goes wrong, so downtuning this for serious analysis
    #https://lichess.org/analysis/standard/rnbqk2r/ppppppbp/5np1/8/2PP4/2N2N2/PP2PPPP/R1BQKB1R_b_KQkq_-_2_4

    #another variation of the above
    #1. d4  Nf6
    #2. c4  g6 (this time g6 less common than e6 so this is a little less effective at inducing KID)
    #3. Nf3 Bg7
    #4. Nc3 O-O
    #transposing to the above position
    ('rnbqk2r/ppppppbp/5np1/8/2PP4/2N2N2/PP2PPPP/R1BQKB1R b KQkq - - 4', 'e8g8'): 0.22,


    #another strategy for reaching the KID
    #1. Nf3 Nf6
    #2. c4  g6
    #3. Nc3 Bg7
    #4. e4  d6
    #5. d4  O-O
    #transposes into the above strong position for white, and again every move other
    #than 2..g6 is easily the most popular for black
    #this time it already seems off the rails after 2..g6, so downweighting that move
    #('rnbqkb1r/pppppppp/5n2/8/2P5/5N2/PP1PPPPP/RNBQKB1R b KQkq - - 2', 'g7g6'): 0.2,

    #one more king's indian trick:
    #1. c4  Nf6
    #2. Nc3 g6
    #3. d4  Bg7
    #4. e4  d6
    #5. Nf3 O-O
    #which transposes into the KID position above. Black should play 3..d5
    #for the Grunfeld but Bg7 is twice as popular for some reason
    ('rnbqkb1r/pppppp1p/5np1/8/2PP4/2N5/PP2PPPP/R1BQKBNR b KQkq - - 3','f8g7'): 0.25,


    #french defense boosted by the "Burn variation", which seems to equalize within a few moves
    #1. e4  e6
    #2. d4  d5
    #3. Nc3 Nf6
    #4. Bg5
    #is this really played as often as 4. e5 ??
    #('rnbqkb1r/ppp2ppp/4pn2/3p4/3PP3/2N5/PPP2PPP/R1BQKBNR w KQkq - - 4', 'c1g5'): 0.5,

    #black's french defense boosted by a 5% chance of white castling here, which is a blunder:
    #https://lichess.org/analysis/standard/r1bq1rk1/pp1nbppp/2n1p3/2ppP3/3P1P2/2N1BN2/PPPQ2PP/R3KB1R_w_KQ_-_6_9
    #('r1bq1rk1/pp1nbppp/2n1p3/2ppP3/3P1P2/2N1BN2/PPPQ2PP/R3KB1R w KQ - - 9', 'e1c1'): 0.25,

    #black's anti-nimzo -> catalan aided by white 15% of Qa4 mistake here:
    #('r1bqkb1r/pppn1ppp/4pn2/8/2pP4/5NP1/PP2PPBP/RNBQK2R w KQkq - - 6', 'd1a4'): 0.25,

    #in the french defense winawer, black benefits because
    #Nf3 is +0.4 for white whereas Qh5 is ~0. However Nf3 is played 4x as often
    #('r1bq1rk1/pp2nppp/2n1p3/2ppP3/3P2Q1/P1PB4/2P2PPP/R1B1K1NR w KQ - - 9', 'g4h5'): 0.5,
    #('r1bq1rk1/pp2nppp/2n1p3/2ppP3/3P2Q1/P1PB4/2P2PPP/R1B1K1NR w KQ - - 9', 'g1f3'): 3,
}

def compute_p1_book(pos, n, optimism=0):
    #return superbook of size N moves that will give the greatest advantage
    if False:
        print()
        print(pos.val)
        print()
        print(chess.Board(pos.val))
        print()

    #TODO: replace all this with a cache singleton
    global LEAF_COUNT


    if pos.total_cnt > DISK_CACHE_THRESHOLD:
        if disk_cache.in_cache(pos.val, n, 1):
            return disk_cache.load_cache(pos.val, n, 1)

    # if pos.total_cnt > CACHE_STATS_THRESHOLD:
    #     #update cache stats
    #     P1_CACHE_STATS.setdefault((pos.val, n),{})
    #     info = P1_CACHE_STATS[(pos.val,n)]
    #     info["cnt"] = info.get("cnt",0) + 1 #number of times encountered
    #     info["last_leaf"] = LEAF_COUNT
    #     info["db_freq"] = pos.total_cnt

    # if (pos.val, n) in P1_CACHE:
    #     return P1_CACHE[(pos.val,n)]

    if pos.is_leaf():
        LEAF_COUNT += 1
        if LEAF_COUNT % 1000 == 0:
            print(f"Leaf count: {LEAF_COUNT}")
        if INCLUDE_PLACEHOLDERS:
            # return SuperBook.placeholder(pos, pos.get_ev(optimism), n)
            return PlaceholderSuperBook(pos, pos.get_ev(optimism), n)
        else:
            return SuperBook(pos, pos.get_ev(optimism))

    superbooks = {} #{node: SuperBook}

    #step 1: compute book for each child node
    for child in pos.children:
        superbooks[child] = compute_p2_book(child, n, optimism = -1 * optimism)

    #now the real computation
    starting_ev = sum([superbooks[child].get_total_ev(0) * pos.probs[child] for child in pos.children])

    #step 2: if we don't include this position in the book
    #        assume we play randomly according to pos.probs
    #        and compute the optimal opening book
    skip_superbook = aggregate_random_books(n, pos.children, pos.probs, superbooks)

    #step 3: if we do include this position in the book
    choose_superbook = SuperBook(pos, starting_ev)

    # for k in range(n): #compute books of size 0 to n-1 moves from the children
    #     #list of positions with at least k moves to learn
    #     options = [c for c in pos.children if superbooks[c].get_size() >= k]
    #     if len(options) == 0: continue

    #     best_child = max(options, key=lambda x: superbooks[x].get_total_ev(k))
    #     best_total_ev = superbooks[best_child].get_total_ev(k)

    #     total_ev = best_total_ev
    #     if k == 0:
    #         moves = [(pos.val,pos.moves[best_child],total_ev)]
    #         choose_superbook.add_book(k+1, OpeningBook(moves), total_ev)
    #     else:
    #         #create an OpeningBook from another book and a new move
    #         #this is a bit of a hack to minimize calls to OpeningBook.get_moves(), which can be time consuming
    #         book_plus_move = (superbooks[best_child].get_book(k), (pos.val,pos.moves[best_child],total_ev))
    #         choose_superbook.add_book(k+1, OpeningBook(None, book_plus_move), total_ev)


    #TODO: remove the commented version above once the new code is working properly
    best_child = max(pos.children, key = lambda x: superbooks[x].get_total_ev(0))
    best_child_ev = superbooks[best_child].get_total_ev(0)
    best_move = (pos.val, pos.moves[best_child],best_child_ev)
    choose_superbook.add_marginal_moves(1, [best_move], [], best_child_ev)
    choose_superbook_moves = set([best_move])
    # choose_superbook.add_book(1, OpeningBook([best_move]), best_child_ev)

    for k, all_books in enumerate(itertools.zip_longest(*[superbooks[c].get_all_books() for c in pos.children])):
        #choose_superbook has 1 move from before the loop: only add up to n-1 additional moves
        if k > n-2: break
        child_to_book = {c:book for c,book in zip(pos.children, all_books)}
        options = [c for c in child_to_book if child_to_book[c] is not None]
        if len(options) == 0: continue

        best_child = max(options, key=lambda x: superbooks[x].get_total_ev(k+1))
        best_total_ev = superbooks[best_child].get_total_ev(k+1)
        best_child_book = child_to_book[best_child]

        total_ev = best_total_ev
        #create an OpeningBook from another book and a new move
        #this is a bit of a hack to minimize calls to OpeningBook.get_moves(), which can be time consuming
        best_move = (pos.val,pos.moves[best_child],total_ev)
        book_plus_move = (child_to_book[best_child], best_move)

        new_choose_superbook_moves = best_child_book.get_moves().union(set([best_move]))
        added_moves = new_choose_superbook_moves.difference(choose_superbook_moves)
        removed_moves = choose_superbook_moves.difference(new_choose_superbook_moves)
        choose_superbook.add_marginal_moves(k+2, added_moves, removed_moves, total_ev)
        choose_superbook_moves = new_choose_superbook_moves
        # choose_superbook.add_book(k+2, OpeningBook(None, book_plus_move), total_ev)

    #step 4: combine skip_superbook (best books if we exclude the current position)
    #and choose_superbook (best books if we do include the currect position)


    # if (pos.val == 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - - 1'):
    # if (pos.val == 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1'): #rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - - 1'):
        # print("book1")
        # print("---")
        # print("---")
        # print("---")
        # print("---")
        # print("---")
        # for mm in skip_superbook.new_marginal_moves:
        #     print(mm)
        # print("book2")
        # print("---")
        # print("---")
        # print("---")
        # print("---")
        # print("---")
        # for mm in choose_superbook.new_marginal_moves:
        #     print(mm)

    superbook = SuperBook(pos, starting_ev)
    superbook_moves = set()
    for k, (skip_book, choose_book) in enumerate(itertools.zip_longest(skip_superbook.get_all_books(), choose_superbook.get_all_books())):
        if skip_book is not None and choose_book is not None:
            skip_ev = skip_superbook.get_total_ev(k+1)
            choose_ev = choose_superbook.get_total_ev(k+1)
            if skip_ev > choose_ev:
                added_moves = skip_book.get_moves().difference(superbook_moves)
                removed_moves = superbook_moves.difference(skip_book.get_moves())
                superbook.add_marginal_moves(k+1, added_moves, removed_moves, skip_ev)
                superbook_moves = set(skip_book.get_moves()) #copy
            else:
                added_moves = choose_book.get_moves().difference(superbook_moves)
                removed_moves = superbook_moves.difference(choose_book.get_moves())
                superbook.add_marginal_moves(k+1, added_moves, removed_moves, choose_ev)
                superbook_moves = set(choose_book.get_moves()) #copy
        elif skip_book is not None:
            skip_ev = skip_superbook.get_total_ev(k+1)
            added_moves = skip_book.get_moves().difference(superbook_moves)
            removed_moves = superbook_moves.difference(skip_book.get_moves())
            superbook.add_marginal_moves(k+1, added_moves, removed_moves, skip_ev)
            superbook_moves = set(skip_book.get_moves()) #copy
        elif choose_book is not None:
            choose_ev = choose_superbook.get_total_ev(k+1)
            added_moves = choose_book.get_moves().difference(superbook_moves)
            removed_moves = superbook_moves.difference(choose_book.get_moves())
            superbook.add_marginal_moves(k+1, added_moves, removed_moves, choose_ev)
            superbook_moves = set(choose_book.get_moves()) #copy

    # superbook = SuperBook(pos, starting_ev)
    # for k, (skip_book, choose_book) in enumerate(itertools.zip_longest(skip_superbook.get_all_books(), choose_superbook.get_all_books())):
    #     if skip_book is not None and choose_book is not None:
    #         skip_ev = skip_superbook.get_total_ev(k+1)
    #         choose_ev = choose_superbook.get_total_ev(k+1)
    #         if skip_ev > choose_ev:
    #             superbook.add_book(k+1, skip_book, skip_ev)
    #         else:
    #             superbook.add_book(k+1, choose_book, choose_ev)
    #     elif skip_book is not None:
    #         skip_ev = skip_superbook.get_total_ev(k+1)
    #         superbook.add_book(k+1, skip_book, skip_ev)
    #     elif choose_book is not None:
    #         choose_ev = choose_superbook.get_total_ev(k+1)
    #         superbook.add_book(k+1, choose_book, choose_ev)

    #TODO: replace once the above loop seems to be working okay
    # for k in range(n):
    #     if skip_superbook.get_size() >= k+1 and choose_superbook.get_size() >= k+1:
    #         skip_ev = skip_superbook.get_total_ev(k+1)
    #         choose_ev = choose_superbook.get_total_ev(k+1)
    #         skip_book = skip_superbook.get_book(k+1)
    #         choose_book = choose_superbook.get_book(k+1)
    #         if skip_ev > choose_ev:
    #             superbook.add_book(k+1, skip_book, skip_ev)
    #         else:
    #             superbook.add_book(k+1, choose_book, choose_ev)
    #     elif skip_superbook.get_size() >= k+1:
    #         skip_ev = skip_superbook.get_total_ev(k+1)
    #         skip_book = skip_superbook.get_book(k+1)
    #         superbook.add_book(k+1, skip_book, skip_ev)
    #     elif choose_superbook.get_size() >= k+1:
    #         choose_ev = choose_superbook.get_total_ev(k+1)
    #         choose_book = choose_superbook.get_book(k+1)
    #         superbook.add_book(k+1, choose_book, choose_ev)

    # if pos.total_cnt > CACHE_THRESHOLD:
    #     print(pos.val, pos.total_cnt)
    #     P1_CACHE[(pos.val,n)] = superbook
    # elif pos.total_cnt > COUNTER_THRESHOLD:
    #     P1_COUNTER[(pos.val,n)] = P1_COUNTER.setdefault((pos.val,n),0) + 1
    #     if P1_COUNTER[(pos.val,n)] * pos.total_cnt >= COUNTER_CACHE_THRESHOLD:
    #         print(pos.val, pos.total_cnt, P1_COUNTER[(pos.val,n)])
    #         P1_CACHE[(pos.val,n)] = superbook


    if pos.total_cnt >= DISK_CACHE_THRESHOLD:
        disk_cache.save_cache(pos.val, n, 1, superbook)

    if pos.total_cnt >= CACHE_STATS_THRESHOLD:
        info = CACHE_STATS.setdefault((pos.val, n, 1),{})
        info["cnt"] = info.get("cnt",0) + 1
        info["last_leaf"] = LEAF_COUNT
        info["pos_cnt"] = pos.total_cnt


    if disk_cache.cnt * n > MAX_CACHED_MOVES:
        #purge 10% of the cache
        cache_score = lambda x: CACHE_STATS[x]["pos_cnt"] * (1 / (math.log(2 + LEAF_COUNT - CACHE_STATS[x]["last_leaf"]))) * (CACHE_STATS[x]["cnt"] / (LEAF_COUNT+1))
        cache_keys = [eval(x) for x in disk_cache.shelf.keys()]
        values = sorted(cache_keys, key = cache_score, reverse=True)
        to_evict = values[round(0.9 * disk_cache.cnt):]
        for (fen, n, player) in to_evict:
            disk_cache.evict(fen, n, player)

    # if pos.total_cnt > CACHE_STATS_THRESHOLD:
    #     P1_CACHE[(pos.val,n)] = superbook


    # if len(P1_CACHE) * n > MAX_CACHED_MOVES:
    #     #purge 10% of the cache
    #     cache_score = lambda x: P1_CACHE_STATS[x]["db_freq"] * (1 / (math.log(2 + LEAF_COUNT - P1_CACHE_STATS[x]["last_leaf"]))) * (P1_CACHE_STATS[x]["cnt"] / (LEAF_COUNT+1))
    #     values = sorted(P1_CACHE.keys(), key = cache_score, reverse = True)
    #     values = values[:round(0.9 * len(P1_CACHE))]
    #     P1_CACHE = {x:P1_CACHE[x] for x in values}

    return superbook

def compute_p2_book(pos, n, optimism=0):
    #compute the book for a node which is the opponent's turn

    global LEAF_COUNT
    global P2_CACHE

    if pos.total_cnt >= DISK_CACHE_THRESHOLD:
        if disk_cache.in_cache(pos.val, n, 2):
            return disk_cache.load_cache(pos.val, n, 2)

    # if pos.total_cnt > CACHE_STATS_THRESHOLD:
    #     #update cache stats
    #     P2_CACHE_STATS.setdefault((pos.val, n),{})
    #     info = P2_CACHE_STATS[(pos.val,n)]
    #     info["cnt"] = info.get("cnt",0) + 1 #number of times encountered
    #     info["last_leaf"] = LEAF_COUNT
    #     info["db_freq"] = pos.total_cnt

    # if (pos.val, n) in P2_CACHE:
    #     return P2_CACHE[(pos.val,n)]

    if pos.is_leaf():
        LEAF_COUNT += 1
        if LEAF_COUNT % 1000 == 0:
            print(f"Leaf count: {LEAF_COUNT}")
        if INCLUDE_PLACEHOLDERS:
            # return SuperBook.placeholder(pos, 1 - pos.get_ev(-1 * optimism), n)
            return PlaceholderSuperBook(pos, 1 - pos.get_ev(-1 * optimism), n)
        else:
            return SuperBook(pos, 1 - pos.get_ev(-1 * optimism))

    superbooks = {}
    for child in pos.children:
        superbooks[child] = compute_p1_book(child, n, optimism = -1 * optimism)


    superbook = aggregate_random_books(n, pos.children, pos.probs, superbooks)

    # if pos.total_cnt > CACHE_THRESHOLD:
    #     print(pos.val, pos.total_cnt)
    #     P2_CACHE[(pos.val,n)] = superbook
    # elif pos.total_cnt > COUNTER_THRESHOLD:
    #     P2_COUNTER[(pos.val,n)] = P2_COUNTER.setdefault((pos.val,n),0) + 1
    #     if P2_COUNTER[(pos.val,n)] * pos.total_cnt >= COUNTER_CACHE_THRESHOLD:
    #         print(pos.val, pos.total_cnt, P2_COUNTER[(pos.val,n)])
    #         P2_CACHE[(pos.val,n)] = superbook


    if pos.total_cnt >= DISK_CACHE_THRESHOLD:
        disk_cache.save_cache(pos.val, n, 2, superbook)

    if pos.total_cnt >= CACHE_STATS_THRESHOLD:
        info = CACHE_STATS.setdefault((pos.val, n, 2),{})
        info["cnt"] = info.get("cnt",0) + 1
        info["last_leaf"] = LEAF_COUNT
        info["pos_cnt"] = pos.total_cnt

    # if pos.total_cnt > CACHE_STATS_THRESHOLD:
    #     P2_CACHE[(pos.val,n)] = superbook

    # if len(P2_CACHE) * n > MAX_CACHED_MOVES:
    #     #purge 10% of the cache
    #     cache_score = lambda x: P2_CACHE_STATS[x]["db_freq"] * (1 / (math.log(2 + LEAF_COUNT - P2_CACHE_STATS[x]["last_leaf"]))) * (P2_CACHE_STATS[x]["cnt"] / (LEAF_COUNT+1))
    #     values = sorted(P2_CACHE.keys(), key = cache_score, reverse = True)
    #     values = values[:round(0.9 * len(P2_CACHE))]
    #     P2_CACHE = {x:P2_CACHE[x] for x in values}

    return superbook

def aggregate_random_books(n, positions, probs, superbooks):
    #if we have a random probability of reaching various positions
    #and prespecified size N superbooks
    #that start from each of those positions
    #what size N superbook should we choose overall?

    #track how many moves we're including from each position's superbook
    #initialize to all zeroes
    cnts = {p:0 for p in positions}

    # if positions and int(positions[0].val.split()[-1]) <= 3:
    #     print("printing aggs")
    #     print([p.val for p in positions])

    #0.5282897987306038
    #0.0036 * math.log(x+1)
    #debug_move = ('rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - - 2', 'c2c4', 0.5375091772533165)
    #0.5365791050653824

    # debug_move = ('rn1q1rk1/4bppp/p2pbn2/1p2p3/4P3/1NN1BP2/PPPQ2PP/2KR1B1R w - - - 11', 'move_9', 0.5163221026503005)
    debug_move = ('rn1q1rk1/4bppp/p2pbn2/1p2p3/4P3/1NN1BP2/PPPQ2PP/2KR1B1R w - - - 1111', 'move_9', 0.5163221026503005) #placeholder
    #debug_child_pos = 'rnbqkb1r/pp1n1ppp/4p3/2ppP3/3P1P2/8/PPP1N1PP/R1BQKBNR b KQkq - - 6' #'rnbqkb1r/ppp2ppp/4pn2/3p2B1/3PP3/2N5/PPP2PPP/R2QKBNR b KQkq - - 4'
    debug_child_pos = 'r1bqkb1r/pp1n1ppp/2n1p3/2ppP3/3P1P2/5N2/PPP1N1PP/R1BQKB1R b KQkq - - 7'

    debug = False
    # debug code
    # if debug_move[0] in [p.val for p in positions]:
    #     print("*******")
    #     print("input")
    #     print("*******")
    #     debug = True
    #     pos = [p for p in positions if p.val == "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - - 2"][0]
    #     for x in superbooks[pos].new_marginal_moves:
    #         print(x)

    #compute starting ev with no opening book
    starting_ev = sum([superbooks[p].get_total_ev(0) * probs[p] for p in positions])

    output_superbook = SuperBook(None, starting_ev)
    total_ev = starting_ev

    # def get_options():
    #     #list of positions with additional moves we haven't picked yet
    #     return [p for p in positions if superbooks[p].get_size() > cnts[p]]

    # print("aggregating")
    # print([p.val for p in positions])

    if debug and (debug_child_pos in [p.val for p in positions]):
        print("printing sub superbook")
        debug_pos = [p for p in positions if p.val == debug_child_pos][0]
        print(f"printing sub position to print: {debug_pos.val}")
        for i, (add_moves, drop_moves) in enumerate(superbooks[debug_pos].new_marginal_moves):
            add_pre = {m[:2] for m in add_moves}
            drop_pre = {m[:2] for m in drop_moves}
            print(superbooks[debug_pos].marginal_evs[i])
            print(superbooks[debug_pos].est_marginal_evs[i])
            print({x for x in add_moves  if x[:2] in add_pre and x[:2] not in drop_pre})
            print({x for x in drop_moves if x[:2] in drop_pre and x[:2] not in add_pre})


    moves_by_fen = {} #fen -> {move}
    options = {x for x in positions if superbooks[x].get_size() > cnts[x]}
    marginal_evs = {x: superbooks[x].get_marginal_ev(cnts[x]+1) * probs[x] for x in positions}
    est_marginal_evs = {x: superbooks[x].get_est_marginal_ev(cnts[x]+1) * probs[x] for x in positions}

    def add(moves1, moves2, update=True, multi=False):
        #add the moves from moves2 to the current set of moves moves1
        #note that this could require subtracting some moves
        #for examples if moves1 has a move for a certain fen
        #and moves2 also has a move for that fen
        #then we need to remove the existing move
        #moves1 = {fen: set(move)}
        #moves2 = {fen: set(move)}
        #return: (set_of_added_moves, set_of_removed_moves)
        added_moves = set()
        removed_moves = set()
        for fen in moves2:
            moves = moves2[fen]
            for move in moves:
                fen = move[0]
                if update:
                    moves1.setdefault(fen,set())
                if fen in moves1:
                    #bugfix: we shouldn't add to removed_moves if move in moves1[fen]
                    if move not in moves1[fen]:
                        abstract = "move" in move[1]
                        if abstract or multi:
                            added_moves.add(move)
                            if update:
                                moves1[fen].add(move)
                        else:
                            added_moves.add(move)
                            removed_moves.update(moves1[fen])
                            if update:
                                moves1[fen] = set([move])
                else:
                    added_moves.add(move)
                    if update:
                        moves1[fen] = set([move])
        return added_moves, removed_moves

    def remove(moves1, moves2, update=True):
        added_moves = set()
        removed_moves = set()
        for fen in moves2:
            moves = moves2[fen]
            for move in moves:
                if fen in moves1:
                    if move in moves1[fen]:
                        removed_moves.add(move)
                    if update:
                        moves1[fen].discard(move)
                        if len(moves1[fen]) == 0:
                            del moves1[fen]
        return added_moves, removed_moves

    def apply_diff(moves1, add_moves, discard_moves, update=True):
        output_add = {}
        output_discard = {}

        add1, remove1 = remove(moves1, discard_moves, update)
        add2, remove2 = add(moves1, add_moves, update)

        for m in add1:
            output_add.setdefault(m[0],set())
            output_add[m[0]].add(m)
        for m in add2:
            output_add.setdefault(m[0],set())
            output_add[m[0]].add(m)

        for m in remove1:
            output_discard.setdefault(m[0],set())
            output_discard[m[0]].add(m)
        for m in remove2:
            output_discard.setdefault(m[0],set())
            output_discard[m[0]].add(m)

        return output_add, output_discard

    def combine_diffs(add_moves1, discard_moves1, add_moves2, discard_moves2):
        output_add = {x: set(add_moves1[x]) for x in add_moves1}
        output_discard = {x: set(discard_moves1[x]) for x in discard_moves1}

        remove(output_discard, add_moves2, update=True)
        remove(output_add, discard_moves2, update=True)
        add(output_discard, discard_moves2, update=True)
        add(output_add, add_moves2, update=True)
        return output_add, output_discard

    #apply_diff -- mutate, no-mutate
    #combine_diffs -- (can do whatever)

    #starting from an empty opening book
    #look through each of the positions and see how much value is gained from
    #memorizing one more move of their opening books
    #greedily choose the one that provides the best marginal ev and repeat N times
    for i in range(n):
        #options = get_options()
        if len(options) == 0: break #no more moves to pick

        next_book_remove = {} #fen -> {move}
        next_book_add = {} #fen -> {move}

        while True:
            #Repeatedly consider learning one more move from the child position with the best marginal ev
            #NOTE: because of overlapping moves incrementing that position doesn't actually mean that our
            #total opening book size increases by 1. it could increase by more than 1 or even decrease

            #we've currently memorized cnts[x] moves from position x
            #compute the marginal value of memorizing one more move from that position
            #NOTE: "marginal_ev" values assume that the opening book moves are of
            #decreasing marginal value which won't necessarily hold, but hopefully isn't too far off

            #get_marginal_ev = lambda x: superbooks[x].get_marginal_ev(cnts[x]+1) * probs[x]

            best_pos = max(options, key = lambda x: est_marginal_evs[x])
            # marginal_ev = get_marginal_ev(best_pos)
            marginal_ev = marginal_evs[best_pos]

            #try incrementing the number of moves from best_pos by 1
            #add roll back if that makes too many moves
            add_moves, discard_moves = superbooks[best_pos].get_marginal_moves(cnts[best_pos]+1) #add_move, discard_moves: {move}

            add_moves_dict = {}
            for move in add_moves:
                fen = move[0]
                add_moves_dict.setdefault(fen,set()).add(move)
            discard_moves_dict = {}
            for move in discard_moves:
                fen = move[0]
                discard_moves_dict.setdefault(fen,set()).add(move)

            tmp_add, tmp_remove = combine_diffs(next_book_add, next_book_remove, add_moves_dict, discard_moves_dict)
            tmp_add, tmp_remove = apply_diff(moves_by_fen, tmp_add, tmp_remove, update=False)

            #TODO: new_size computation not very accurate, think about how to fix it
            new_size = sum(len(moves_by_fen[x]) for x in moves_by_fen)
            new_size += sum(len(tmp_add[x]) for x in tmp_add)
            new_size -= sum(len(tmp_remove[x]) for x in tmp_remove)

            if debug and (debug_child_pos in [p.val for p in positions]):
                print(f"debug pos: {len(output_superbook.new_marginal_moves)}")
                print(best_pos.val, cnts[best_pos])
                print([(p.val,cnts[p],marginal_evs[p], est_marginal_evs[p]) for p in cnts])
                print(add_moves)
                print(discard_moves)
                print(tmp_add)
                print(tmp_remove)
                print("moves_by_fen")
                print(moves_by_fen)
                print(f"new_size: {new_size}, {i+1}")

            if debug and (debug_move in add_moves or debug_move in discard_moves):
                print("moves_by_fen")
                print(moves_by_fen)
                print("add discard moves")
                print(add_moves)
                print(discard_moves)
                print(tmp_add, tmp_remove)

            if new_size > i+1:
                #break out of the loop, we can't add another move
                break
            else:
                next_book_add, next_book_remove = combine_diffs(next_book_add, next_book_remove, add_moves_dict, discard_moves_dict)

                if debug and (debug_move in add_moves or debug_move in discard_moves):
                    print("next book add/remove")
                    print(next_book_add, next_book_remove)

                if debug and (debug_child_pos in [p.val for p in positions]):
                    print("next book add/remove")
                    print(next_book_add, next_book_remove)


                cnts[best_pos] = cnts[best_pos] + 1
                if superbooks[best_pos].get_size() > cnts[best_pos]:
                    marginal_evs[best_pos] = superbooks[best_pos].get_marginal_ev(cnts[best_pos]+1) * probs[best_pos]
                    est_marginal_evs[best_pos] = superbooks[best_pos].get_est_marginal_ev(cnts[best_pos]+1) * probs[best_pos]
                else:
                    #remove best_pos from options
                    options.discard(best_pos)
                total_ev += marginal_ev

            #after incrementing a few times we're out of options then break out of the loop
            #and add to superbook
            #options = get_options()
            if len(options) == 0:
                break

        if debug and ((debug_move[0] in next_book_add and debug_move in next_book_add[debug_move[0]]) or (debug_move[0] in next_book_remove and debug_move in next_book_remove[debug_move[0]])):
            print("applying diff")
            print(moves_by_fen)
            print(next_book_add)
            print(next_book_remove)

        #compute new moves to add and old moves to remove
        tmp_add, tmp_remove = apply_diff(moves_by_fen, next_book_add, next_book_remove)

        if sum(len(moves_by_fen[x]) for x in moves_by_fen) > i+1:
            print("oversized superbook")
            print(i+1)
            print(moves_by_fen)
            print(next_book_add)
            print(next_book_remove)
            print(tmp_add)
            print(tmp_remove)
            raise

        add_set = set().union(*tmp_add.values())
        remove_set = set().union(*tmp_remove.values())

        if debug and ((debug_move[0] in next_book_add and debug_move in next_book_add[debug_move[0]]) or (debug_move[0] in next_book_remove and debug_move in next_book_remove[debug_move[0]])):
            print("tmp_add, tmp_remove")
            print(tmp_add, tmp_remove)
            print("add/remove set")
            print(add_set, remove_set)
            print("positions")
            print([p.val for p in positions])

        for x in add_set:
            if x in remove_set:
                print(add_set)
                print(remove_set)
                raise

        # if len(add_set) == 0:
        #     print("empty add!")
        #     print([p.val for p in positions])
        #     print(f"cnt: {len(output_superbook.new_marginal_moves)}")
        #     print(add_set)
        #     print(remove_set)
        #     print(moves_by_fen)
        #     print(next_book_add)
        #     print(next_book_remove)
        #     raise

        #TODO: what to do when we're aggregating from two subbooks
        #that each include the same move (transpositions)
        if any([est_marginal_evs[p] == 0 and probs[p] != 0 for p in positions]):
            print("zero marginal value")
            zero_pos = [p for p in positions if est_marginal_evs[p] == 0][0]
            print({p.val: (cnts[p],est_marginal_evs[p]) for p in positions})
            print("prob")
            print(probs[zero_pos])
            print(f"book size: {zero_pos.val} - {len(superbooks[zero_pos].new_marginal_moves)}")
            for i in range(len(superbooks[zero_pos].new_marginal_moves)):
                print(superbooks[zero_pos].new_marginal_moves[i], superbooks[zero_pos].est_marginal_evs[i])
            raise

        output_superbook.add_marginal_moves(i+1, add_set, remove_set, total_ev) #OpeningBook(list(moves))

    if debug and ((debug_move[0] in [p.val for p in positions]) or (debug_child_pos in [p.val for p in positions])):
        print("*******")
        print("output")
        print("*******")
        print([p.val for p in positions])
        print(f"book size: {len(output_superbook.new_marginal_moves)}")
        pos = [p for p in positions if (p.val == debug_move[0] or p.val == debug_child_pos)][0]
        for i in range(len(output_superbook.new_marginal_moves)):
            print(output_superbook.new_marginal_moves[i], output_superbook.marginal_evs[i])

    return output_superbook


#from the python documentation
#https://code.activestate.com/recipes/576694/
class OrderedSet(collections.MutableSet):
    def __init__(self, iterable=None):
        self.end = end = []
        end += [None, end, end]         # sentinel node for doubly linked list
        self.map = {}                   # key --> [key, prev, next]
        if iterable is not None:
            self |= iterable

    def __len__(self):
        return len(self.map)

    def __contains__(self, key):
        return key in self.map

    def add(self, key):
        if key not in self.map:
            end = self.end
            curr = end[1]
            curr[2] = end[1] = self.map[key] = [key, curr, end]

    def discard(self, key):
        if key in self.map:
            key, prev, next = self.map.pop(key)
            prev[2] = next
            next[1] = prev

    def __iter__(self):
        end = self.end
        curr = end[2]
        while curr is not end:
            yield curr[0]
            curr = curr[2]

    def __reversed__(self):
        end = self.end
        curr = end[1]
        while curr is not end:
            yield curr[0]
            curr = curr[1]

    def pop(self, last=True):
        if not self:
            raise KeyError('set is empty')
        key = self.end[1][0] if last else self.end[2][0]
        self.discard(key)
        return key

    def __repr__(self):
        if not self:
            return '%s()' % (self.__class__.__name__,)
        return '%s(%r)' % (self.__class__.__name__, list(self))

    def __eq__(self, other):
        if isinstance(other, OrderedSet):
            return len(self) == len(other) and list(self) == list(other)
        return set(self) == set(other)

class OpeningBook:
    #contains the optimal opening book with <= N moves
    def __init__(self, moves=None, book_plus_move=None):
        super()
        self.moves = moves #set([(fen, move, ev)])  # ev just there for printing later
        self.book_plus_move = book_plus_move
    def get_moves(self):
        if self.book_plus_move:
            book,move = self.book_plus_move
            return book.get_moves() + [move]
        else:
            return self.moves

class PlaceholderOpeningBook:
    def __init__(self, position, N, total_ev):
        #N is 1 indexed
        self.position = position
        self.N = N
        self.total_ev = total_ev
    def get_move(self, i):
        #i is 0 indexed
        return (self.position.val, f"move_{i}", self.total_ev)
    def get_moves(self):
        return [self.get_move(i) for i in range(self.N)]

class SuperBook:
    #For all i in 1,..N contains the opening book of <= i moves
    #along with the expected value for using that opening book
    def __init__(self, position, starting_ev):
        super()
        self.position = position
        self.starting_ev = starting_ev
        self.books = [] #TODO: remove
        self.marginal_moves = {} #{k: [(added_moves, removed_moves)]} #TODO: remove
        #once new_marginal_moves is working, replace self.marginal_moves
        self.new_marginal_moves = [] #[(added_moves, removed_moves)]
        self.total_evs = []
        self.marginal_evs = []
        self.est_marginal_evs = []
    @staticmethod
    def placeholder(position, starting_ev, move_cnt):
        sb = SuperBook(position, starting_ev)
        for i in range(move_cnt):
            total_ev = starting_ev + OUT_OF_BOOK_PREP_VALUE(i+1)
            #moves = [(position.val, f"move_{j}") for j in range(i)]
            #PlaceholderOpeningBook(position, move_cnt)

            #sb.add_book(i+1, PlaceholderOpeningBook(position, i+1, total_ev), total_ev)
            new_move = (position.val, f"move_{i}", total_ev)
            sb.add_marginal_moves(i+1, [new_move], [], total_ev)
        return sb
    def add_book(self, i, book, total_ev):
        #TODO: remove, concept of books replaces with marginal_moves
        if len(self.books) != i-1:
            print(i)
            print(self)
            raise
        self.books.append(book) #OpeningBook(i, moves))
        self.total_evs.append(total_ev)
        if i == 1:
            self.marginal_evs.append(total_ev - self.starting_ev)
            self.est_marginal_evs.append(total_ev - self.starting_ev)
            self.new_marginal_moves.append((book.get_moves(),[]))
        else:
            self.marginal_evs.append(self.total_evs[i-1] - self.total_evs[i-2])
            self.est_marginal_evs.append(self.total_evs[i-1] - self.total_evs[i-2])
            if isinstance(self.books[i-1],PlaceholderOpeningBook) and \
               isinstance(self.books[i-2],PlaceholderOpeningBook) and \
               self.books[i-1].position == self.books[i-2].position:
                self.new_marginal_moves.append(([self.books[i-1].get_move(i-1)],[]))
            else:
                moves_new = self.books[i-1].get_moves()
                moves_old = self.books[i-2].get_moves()
                added_moves = set(moves_new).difference(set(moves_old))
                removed_moves = set(moves_old).difference(set(moves_new))
                self.new_marginal_moves.append((list(added_moves), list(removed_moves)))

    def add_marginal_moves(self, i, added_moves, removed_moves, total_ev):
        self.new_marginal_moves.append((added_moves, removed_moves))
        self.total_evs.append(total_ev)

        if i == 1:
            self.marginal_evs.append(total_ev - self.starting_ev)
            self.est_marginal_evs.append(total_ev - self.starting_ev)
        else:
            marginal_ev = self.total_evs[i-1] - self.total_evs[i-2]
            if marginal_ev == 0:
                #marginal_ev of 0 causes problems: the greedy algorithm will never add that
                #move even if there are valuable moves after it
                #so smooth the evs for now to avoid marginal_ev = 0
                self.est_marginal_evs.append(self.est_marginal_evs[i-2] * 0.9)
            elif len([x for x in added_moves if "move" in x[1]]) - len([x for x in removed_moves if "move" in x[1]]) == 1:
                #added an abstract move -- use the real marginal_ev as the est_marginal_ev
                self.est_marginal_evs.append(marginal_ev)
            else:
                # if marginal_ev < 0.1 * self.marginal_evs[i-2] and marginal_ev < 10**-5:
                #     print("major decline")
                #     print(marginal_ev)
                #     print(self.est_marginal_evs[i-2])
                #     print(added_moves)
                #     print(removed_moves)
                #     print("printing superbook")
                #     for i, (add_moves, drop_moves) in enumerate(self.new_marginal_moves):
                #         add_pre = {m[:2] for m in add_moves}
                #         drop_pre = {m[:2] for m in drop_moves}
                #         print("ev")
                #         print(self.marginal_evs[i])
                #         print(self.est_marginal_evs[i])
                #         print(add_pre)
                #         print(drop_pre)
                #     raise
                self.est_marginal_evs.append(min(max(marginal_ev, self.est_marginal_evs[i-2] * 0.8), self.est_marginal_evs[i-2] * 1.2))
            self.marginal_evs.append(marginal_ev)
    def get_total_ev(self, k):
        #EV of learning the book with (up to) k moves
        if k==0:
            return self.starting_ev
        else:
            return self.total_evs[k-1]
    def get_marginal_ev(self, k):
        return self.marginal_evs[k-1]
    def get_est_marginal_ev(self, k):
        return self.est_marginal_evs[k-1]
    def get_book(self, k):
        #deprecated, remove after a while 2020-03-22
        return self.books[k-1]
    def get_all_books(self):
        moves = set()
        for added_moves, removed_moves in self.get_all_marginal_moves():
            moves.update(added_moves)
            moves.difference_update(removed_moves)
            yield OpeningBook(moves)
    def get_marginal_moves(self, k):
        #k is one-indexed
        #return diff between
        #the moves in self.books[k-1]
        #and the moves in self.books[k-2]
        return self.new_marginal_moves[k-1]
    def get_all_marginal_moves(self):
        for i in range(self.get_size()):
            yield self.get_marginal_moves(i+1)
    def get_size(self):
        return len(self.new_marginal_moves)
    def __str__(self):
        return str(self.position) + '\n' +\
               str(self.starting_ev) + '\n' +\
               str(self.books) + '\n' +\
               str(self.total_evs) + '\n' +\
               str(self.marginal_evs)

class PlaceholderSuperBook(SuperBook):
    def __init__(self, position, starting_ev, N):
        self.position = position
        self.starting_ev = starting_ev
        self.N = N
        self.new_marginal_moves = []
        self.total_evs = []
    def get_total_ev(self, k):
        #EV of learning the book with (up to) k moves
        return self.starting_ev + OUT_OF_BOOK_PREP_VALUE(k)
    def get_marginal_ev(self, k):
        return OUT_OF_BOOK_PREP_VALUE(k) - OUT_OF_BOOK_PREP_VALUE(k-1)
    def get_est_marginal_ev(self, k):
        return OUT_OF_BOOK_PREP_VALUE(k) - OUT_OF_BOOK_PREP_VALUE(k-1)
    def get_marginal_moves(self, k):
        marginal_move = (self.position.val, f"move_{k-1}", self.get_total_ev(k))
        return ([marginal_move],[])
    def get_size(self):
        return self.N

class GameNode:
    def __init__(self, val):
        super()
        self.val = val #fen
        #must run set_info before using the node
        self.children = None #[child node]
        self.moves = None #{child node: name of move}
        self.probs = None #{child node: prob of move}
    def is_leaf(self):
        return len(self.children) == 0
    def set_info(self, children, moves, probs, total_cnt):
        self.children = children
        self.moves = moves
        self.probs = probs
        self.total_cnt = total_cnt
    def get_ev(self, optimism):
        #average across the evaluations of the children, weighted by their probabilities
        #only allow this for leaf nodes
        if self.is_leaf():
            return evaluate_pseudo_fen(self.val,EVAL_TIME,optimism)[1]
        else:
            raise
    def __str__(self):
        return str(self.val) + '\n' + str(self.probs)


def pseudo_fen_plus_move(fen, move):
    fen = fen.split()
    fen[-2] = "0"
    fen = " ".join(fen)

    fen = fen_plus_move(fen, move)

    fen = fen.split()
    fen[-2] = "-"
    fen = " ".join(fen)
    return fen

def move_history_to_pseudo_fen(move_history):
    fen = move_history_to_fen(move_history)

    fen = fen.split()
    fen[-2] = "-"
    fen = " ".join(fen)
    return fen

def evaluate_pseudo_fen(fen, time, optimism = 0):
    fen = fen.split()
    fen[-2] = "0"
    fen = " ".join(fen)

    move, eval_ = EVALUATOR.evaluate_ev(fen, time)
    time = EVALUATOR.get_eval_time(fen) #time in millis

    nodes = 1000 * 1000 * (time / 1000) #~1M nodes per second
    log2_nodes = math.log(nodes) / math.log(2)

    def sigmoid(x, L ,x0, y0, k):
        y = L / (1 + np.exp(-k*(x-x0))) + y0
        return (y)

    #fit based on this graph: http://www.talkchess.com/forum3/viewtopic.php?t=72834
    elo = sigmoid(log2_nodes, 3.30869470e+03, 1.34955266e+01, 4.88409556e+02, 2.87964204e-01)

    #error decreases linearly with elo from here:
    #https://rjlipton.wordpress.com/2016/11/30/when-data-serves-turkey/
    error = 1/20000 * (3797 - elo) #on the order of .02

    return move, eval_ + error * optimism

def print_pseudo_fen(fen):
    fen = fen.split()
    fen[-2] = "0"
    fen = " ".join(fen)

    print(chess.Board(fen))


def generate_position_stats():
    positions = {} #fen -> {fen, move_cnts:{move: cnt}, total_cnt}

    #position info
    cnt = 0
    with open(INPUT_FILE) as csvfile:
        reader = csv.DictReader(csvfile)
        move_history_to_fen_cache = {}
        fen_plus_move_cache = {}
        for row in reader:
            cnt += 1
            if (cnt % 1000 == 0): print(cnt)

            move_cnts = eval(row["move_cnts"])

            #use this for quick tests
            # if (sum(move_cnts[x] for x in move_cnts) < 10000): continue #MUST: REMOVE

            move_history = eval(row["move_history"])

            fen = row["fen"]

            if fen == "rnbqk2r/ppppppbp/5np1/8/2PPP3/5N2/PP3PPP/RNBQKB1R b KQkq - - 4": #guess this only comes up in pre-moves and is extremely successful there
                move_cnts["f6e4"] = 100
                print("hard coding f6e4 in this position: rnbqk2r/ppppppbp/5np1/8/2PPP3/5N2/PP3PPP/RNBQKB1R b KQkq - - 4")

            positions[fen] = {"fen":fen, "move_cnts":move_cnts, "move_history": str(move_history)}
            #set child info if not set
            for move in move_cnts:
                child_fen = pseudo_fen_plus_move(fen, move)
                full_move_list = str(eval(row["move_history"]) + [move])
                default = {"fen": child_fen, "move_cnts":{}, "move_history":full_move_list}
                positions.setdefault(child_fen,default)

            #set best move info if not set
            best_move = evaluate_pseudo_fen(fen,EVAL_TIME)[0]
            best_move_fen = pseudo_fen_plus_move(fen, best_move)
            full_move_list = str(move_history + [best_move])
            default = {"fen": best_move_fen, "move_cnts":{}, "move_history":full_move_list}
            positions.setdefault(best_move_fen, default)


    #warn if any positions have >0 and <20 moves --
    #this small n can ruin the data:
    #eg: make sure to play move X, which leads to a single game where the opponent
    #blunders their queen a few moves down the line
    for fen in positions:
        if sum(positions[fen]["move_cnts"].values()) > 0 and sum(positions[fen]["move_cnts"].values()) < 20:
            print('WARNING: positions with limited move counts')
            print(positions[fen]["move_history"])
            print(sum(positions[fen]["move_cnts"].values()))


    #compute move probabilities (these are the edge weights)
    for fen in positions:
        info = positions[fen]
        info.setdefault("probs",{})
        fen = info["fen"]

        #set counts
        total_cnt = 0
        total_weight = 0

        for move in info["move_cnts"]:
            prob_mult = PROBABILITY_MULTIPLIERS.get((fen, move),1)
            if PLAYER_STRENGTH:
                total_weight += (info["move_cnts"][move] * prob_mult) ** PLAYER_STRENGTH
            else:
                total_weight += (info["move_cnts"][move] * prob_mult)
            total_cnt += info["move_cnts"][move]

        #set probs
        for move in info["move_cnts"]:
            child_fen = pseudo_fen_plus_move(fen, move)
            prob_mult = PROBABILITY_MULTIPLIERS.get((fen, move),1)
            if PLAYER_STRENGTH:
                weight = (info["move_cnts"][move] * prob_mult) ** PLAYER_STRENGTH
            else:
                weight = (info["move_cnts"][move] * prob_mult)
            info["probs"][move] = weight / total_weight

        #set total cnt
        info["total_cnt"] = total_cnt

        #add best_move as an edge with weight 0
        if total_cnt > 0: #skip this step for leaf nodes
            best_move = evaluate_pseudo_fen(fen,EVAL_TIME)[0]
            info["probs"].setdefault(best_move,0)
    return positions

def generate_game_tree(positions):
    #generate basic nodes for each position
    nodes = {} #fen -> node
    for fen in positions:
        nodes[fen] = GameNode(positions[fen]["fen"])

    #create graph by fully initializing node information
    for fen in nodes:
        info = positions[fen]
        fen = info["fen"]

        children = []
        moves = {}
        probs = {}

        #set children, probs, moves
        for move in positions[fen]["probs"]:
            child_fen = pseudo_fen_plus_move(fen, move)
            full_move_list = str(eval(positions[fen]["move_history"]) + [move])
            child_node = nodes[child_fen]

            children.append(child_node)
            moves[child_node] = move
            probs[child_node] = positions[fen]["probs"][move]

        nodes[fen].set_info(children, moves, probs, info["total_cnt"])

    return nodes

def print_book(superbook, name):
    print(superbook.get_total_ev(0))
    #note: the best book might not be the one with the most moves!
    #TODO: throw out all too-large books
    #TODO: figure out how to augment the game tree such that more
    #      moves is always better
    for i in range(superbook.get_size()):
        # if x["marginal_ev"] <= 0:
        #     break
        print(i+1,superbook.get_total_ev(i+1) - superbook.get_total_ev(0))
    #

    #remove below once we haven't used get_book in a while 2020-03-22
    #all_books = [(superbook.get_book(i),superbook.get_total_ev(i),len(superbook.get_book(i).get_moves()),i) for i in range(1,superbook.get_size()+1)]
    all_books = [(book,superbook.get_total_ev(i+1),len(book.get_moves()),i+1) for i,book in enumerate(superbook.get_all_books())]

    best_book, best_ev, move_cnt, best_i = max(all_books, key = lambda x: x[1])
    print(best_i)
    print('move cnt:' + str(len(best_book.get_moves())))
    moves = [m for m in best_book.get_moves() if m]

    #testing:
    print("superbook marginal moves")
    for i, (add_moves, drop_moves) in enumerate(superbook.new_marginal_moves):
        add_pre = {m[:2] for m in add_moves}
        drop_pre = {m[:2] for m in drop_moves}
        print("ev")
        print(superbook.marginal_evs[i])
        print(superbook.est_marginal_evs[i])
        print({x for x in add_moves  if x[:2] in add_pre and x[:2] not in drop_pre})
        print({x for x in drop_moves if x[:2] in drop_pre and x[:2] not in add_pre})

    with open(f"/tmp/{name}_opening_book.txt", "w") as f_out:
        for m in sorted(moves, key=lambda x: x[0]):
            fen = m[0]
            #print_pseudo_fen(fen)
            f_out.write(str(m) + '\n')
            print(m)
            # print(positions[fen]["move_cnts"])
            # print(positions[fen]["total_cnt"])

def get_book_info(book_hash, start_node, start_node_prob, move_cnt):
    #NOTE: this doesn't account for transpositions
    #return most common leaves and the biggest opponent errors by expected_value
    #given the opening book
    if start_node.is_leaf():
        leaves = [(start_node.val, start_node_prob)]
        errors = []
        return leaves, errors
    elif start_node.val in book_hash:
        child_fen = pseudo_fen_plus_move(start_node.val,book_hash[start_node.val][1])
        child = [x for x in start_node.children if x.val == child_fen][0]
        return get_book_info(book_hash, child, start_node_prob, move_cnt)
    else:
        #compute most probable leaves
        leaves = []

        #compute biggest errors, ie which moves outside of the opening book
        #(ie usually enemy moves) are the biggest mistakes
        errors = []

        #best move for the enemy has the minimum value for us (evs here are from our perspective)
        all_evs = [book_hash[child.val][2] for child in start_node.children if child.val in book_hash]

        if all_evs:
            best_child_ev = min(all_evs)
            for child in start_node.children:
                move_prob = start_node.probs[child]
                move = start_node.moves[child]
                if child.val in book_hash:
                    #compute the amount the enemy loses from the move
                    loss = book_hash[child.val][2] - best_child_ev
                    weighted_loss = loss * start_node_prob * move_prob
                    errors.append((start_node.val, move, weighted_loss))

        #add the values from the child nodes
        for child in start_node.children:
            prob = start_node_prob * start_node.probs[child]
            child_leaves, child_errors = get_book_info(book_hash, child, prob, move_cnt)
            leaves += child_leaves
            errors += child_errors

        leaves.sort(key = lambda x: x[1], reverse = True)
        leaves = leaves[:move_cnt]
        errors.sort(key = lambda x: x[2], reverse = True)
        errors = errors[:move_cnt]

        return leaves, errors

def generate_book(starting_fen, move_cnt, side, nodes):
    #reset the global caches
    global CACHE_STATS

    CACHE_STATS = {}

    start_node = nodes[starting_fen]
    print("generating book")
    if side == "white":
        superbook = compute_p1_book(start_node, move_cnt, 0)
    elif side == "black":
        superbook = compute_p2_book(start_node, move_cnt, 0)
    else:
        raise
    print_book(superbook, side)

    CACHE_STATS = {}

    #Refine evaluations:
    #the above evaluations are 1 second per move, which gives some inaccuracies
    #and the opening book will suggest some moves that look good based on 1 second
    #of evaluation but wouldn't after a longer evaluation. So after computing the opening book,
    #rerun the most common positions with a longer eval (10 seconds)
    #and then generate the opening book again. Can iterate on this if necessary
    print("refining evaluations")

    starting_fen = move_history_to_pseudo_fen(str(starting_history))
    book = list(superbook.get_all_books())[-1] #.get_book(superbook.get_size()) #biggest book in the superbook
    book_hash = {} #fen: (fen, move, total_ev)
    for x in book.get_moves():
        #in the case of leaves with multiple move_0, move_1...
        #store the maximum value
        fen = x[0]
        value = x[2]
        if fen not in book_hash or value > book_hash[fen][2]:
            book_hash[fen] = x

    top_leaves, biggest_errors = get_book_info(book_hash, start_node, 1, 250) #top 250 positions
    print(top_leaves)
    print(biggest_errors)
    for fen,prob in top_leaves:
        evaluate_pseudo_fen(fen, 8000 * EVAL_TIME * prob)[1] #compute these nodes in depth proportional to their likelihood
    print("done refining evaluations")

if __name__ == "__main__":
    #move_history -> {fen, move_cnts:{move: cnt}, total_cnt}
    positions = generate_position_stats()

    print(f"position cnt: {len(positions)}")
    print(sys.getsizeof(positions))

    #game tree
    #nodes contain list of children
    #along with the probability,
    nodes = generate_game_tree(positions)

    starting_history = [] #['e2e4', 'e7e5'] #['e2e4', 'g8f6'] #['e2e4', 'g8f6', 'e4e5', 'f6d5']
    starting_fen = move_history_to_pseudo_fen(str(starting_history))
    # starting_fen = 'rnbqkb1r/ppp2ppp/4pn2/3p4/3PP3/2N5/PPP2PPP/R1BQKBNR w KQkq - - 4'
    # starting_fen = 'rnbqkb1r/pppn1ppp/4p3/3pP3/3P4/2N5/PPP2PPP/R1BQKBNR w KQkq - - 5'
    start_node = nodes[starting_fen]

    move_cnt = 1000

    # generate_book(starting_fen, move_cnt, "white", nodes)
    generate_book(starting_fen, move_cnt, "black", nodes) #MUST: CLEAR OUT THE COUNTERS INSIDE generate_book


    print(LEAF_COUNT)

    EVALUATOR.save_evals()
