import csv
import chess
import chess.engine
import random
import math

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve()))
from run_maia import fen_to_probs

#TODOS:
#1) [DONE] cache superbooks so we don't do them repeatedly (~5x speedup on filtered_moves_1000)
#2) speed up superbook calc, maybe by using marginal moves? Want to scale to 5-10k
#3) [IN PROGRESS] rerun on larger position set (max 50 instead of max 1000).
#3a) [DONE] cycle detection to fix max 50 scenario
#3b) rerun on even larger (max 10-20 instead of max 50). Needs additional stockfish evals, also more cycle avoidance
#4) at the end of a run, find the leaves, add move history and/or run maia on those and save the probabilities
#load the probabilities at the start of the next run to include those moves in the tree
#5) [DONE] add biggest blunders separate from biggest errors
#maybe) generate superbooks for different lichess skill levels
#maybe) apply the optimism score into the placeholder superbook -- optimism score should result in more exploration overall
#TODO) Debug why leaf study counts aren't proportional to leaf frequency
#TODO) check for "tricky positions" defined as maia evals that have blunder chances

#skip moves that lead to repetitions and cycles in the opening tree graph
#this is slightly unnatural but isn't too common
#generally removing the white move from the cycle that was least probable (since repetition can be good for black)
disallowed_moves = {
    "rnbqkb1r/1p2pppp/p2p4/8/3NP1n1/2N1B3/PPP2PPP/R2QKB1R w KQkq - 0 1": ["e3c1"], #common but gives black a repetition, also e3g5 is more common
    "r1bqkb1r/1p1npppp/p1p2n2/2Pp4/3P4/2N2N2/PP1BPPPP/R2QKB1R w KQkq - 0 1": ["d2f4"],
    "r2q1rk1/pb1nbppp/1pp1pn2/3pN3/2PP4/6P1/PPQBPPBP/RN1R2K1 w - - 0 1": ["d2f4"],
    "rn1q1rk1/1bp1bppp/p3pn2/1p6/3P4/5NP1/PP1BPPBP/RNQ2RK1 w - - 0 1": ["c1c2"],
    "r2qr1k1/1bp1bppp/p1np1n2/1p2p3/3PP3/1BP2N1P/PP3PP1/RNBQR1K1 w - - 0 1": ["f3g5"],
    "rnbq1rk1/pp2ppbp/6p1/3pN3/3P2n1/6P1/PP2PPBP/RNBQ1RK1 w - - 0 1": ["e5f3"],
    "rnbq1rk1/pp3pbp/4pnp1/3p4/3P4/2N2NP1/PP2PPBP/R1BQ1RK1 w - - 0 1": ["f3e5"],
    "rnbq1rk1/pp2ppbp/6p1/3n4/3N4/6P1/PP2PPBP/RNBQ1RK1 w - - 0 1": ["d4b5"],
    "2rq1rk1/p2nbppp/bpp1pn2/3p4/2PP4/1PN2NP1/P1Q1PPBP/R1BR2K1 w - - 0 1": ["c1f4"],
    "r2q1rk1/pb1nbppp/1pp1p3/3pN2n/2PP1B2/6P1/PPQ1PPBP/RN1R2K1 w - - 0 1": ["f4c1"],
    "r2q1rk1/pb1nbppp/1pp1pn2/3p4/2PP4/2N2NP1/PPQ1PPBP/R1BR2K1 w - - 0 1": ["c1f4"],
    "r1bq1rk1/pp1nbppp/2p1pn2/3p4/2PP4/5NP1/PPQ1PPBP/RNB2RK1 w - - 0 1": ["c1f4"],
    "r1bq1rk1/1p2bppp/p1n1pn2/8/P1BPQ3/2N2N2/1P3PPP/R1BR2K1 w - - 0 1": ["e4e2"],
    "r1bqk1nr/pp1pppbp/2n3p1/8/2P1P3/1N2B3/PP3PPP/RN1QKB1R w KQkq - 0 1": ["b3d4"],
    "r1bqkb1r/pp3p1p/2n1p1p1/3n4/3P4/1QN2N2/PP3PPP/R1B1KB1R w KQkq - 0 1": ["c1g5"],
    "r1bqkb1r/pp3p1p/2n1p1p1/8/2BP4/BQP2N2/P4PPP/R3K2R w KQkq - 0 1": ["a3c1"],
    "rn3rk1/pb2ppbp/1p4p1/1B6/3PP3/5N2/q2B1PPP/1RQ2RK1 w - - 0 1": ["b5c4"],
    "rnbqkb1r/pp2pppp/8/2p5/2B1P3/2Nn1N2/PP1P1PPP/R1BQ1K1R w kq - 0 1": ["f1e2"], #common but gives black a repetition, also d1e2 more common
    "r1bqkb1r/5ppp/p1np1n2/1p1Np3/4P3/N7/PPPB1PPP/R2QKB1R w KQkq - 0 1": ["d2g5"], #most common! confirm strong white won't actually repeat?
    "r2q1rk1/pp2bpp1/2npbn1p/4p3/4P3/2N2N1P/PPPB1PP1/R2QRBK1 w - - 0 1": ["d2c1"], #most common but a2a3 is fine
    "rnbq1rk1/ppp2pb1/3p1npp/4p3/2PPP3/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 1": ["c1e3"],
    "r1bqkb1r/pp2pppp/2n2n2/3p4/3P4/2N2N2/PP1BPPPP/R2QKB1R w KQkq - 0 1": ["d2f4"], #most common! confirm strong white won't actually repeat?
    "rnbqkb1r/pp2pppp/2p2n2/8/P1pP3N/2N5/1P2PPPP/R1BQKB1R w KQkq - 0 1": ["h4f3"],
    "r1bqk2r/ppp2ppp/2n5/3n4/Q1BP4/5N2/PP1N1PPP/R3K2R w KQkq - 0 1": ["a4b3"], #most common! confirm strong white won't actually repeat?
    "r1bqkb1r/ppp2ppp/8/3pP3/P2Q4/8/1PP2PPP/RNB2RK1 w kq d6 0 1": ["e5d6"], #most common, looks like white wants a draw here
    "r1bq1rk1/2p1bppp/p1np1n2/1p2p1N1/4P3/1BP4P/PP1P1PP1/RNBQR1K1 w - - 0 1": ["g5f3"], #most common but d2d4 is fine
    "r2qkb1r/2Rb1ppp/pB2p3/3pP3/5P2/2N5/P1PQ2PP/4K2R w Kkq - 0 1": ["c7b7"],
    "rn1qkb1r/pp1bpppp/3p4/8/3NP1n1/2N1B3/PPP2PPP/R2QKB1R w KQkq - 0 1": ["e3c1"],
    "r1bqkb1r/1p1npppp/p1p5/2Pp3n/3P1B2/2N2N2/PP2PPPP/R2QKB1R w KQkq - 0 1": ["f4c1"],
    "r1bqkb1r/pp1n1ppp/2p5/3p3n/3P1B2/2N2N2/PPQ1PPPP/R3KB1R w KQkq - 0 1": ["f4d2"], #most common by a bit
    "rn3rk1/p3ppbp/1p4p1/8/3PP1b1/4BN2/1q2BPPP/R2Q1RK1 w - - 0 1": ["a1b1"], #rook vs queen standoff, new position
    "r1b1kb1r/pp1n1ppp/1qn1p3/3pP3/3N1P2/2N1B3/PPP3PP/R2QKB1R w KQkq - 0 1": ["c3a4"],
    "3r1k2/p2Pr2p/1p1B4/2p3b1/2B5/8/P3R1PP/6K1 w - - 0 1": ["c4b5"],
}

EVAL_TIME = 1
STRENGTH = 1.6 #plays the right move 90/10 instead of 80/20
MISSING_MOVES = {
    'r2r2k1/pp2ppb1/6pp/n2PP3/6b1/5N2/qR2BPPP/2BQR1K1 b - - 0 1': {'a2a1': 10},
    '1r1qk2r/p2pbppp/4p3/2p1P3/2Pn4/3Q2P1/PP3PBP/1RB1R1K1 b k - 0 1': {'a7a5': 1},
    'rn1q4/pb3kb1/2p1pn1p/1p2P1p1/2pP4/2N3B1/PP3PPP/R2QK2R b KQ - 0 1': {'f6h7': 4}, #4/4 in lichess
}
PROBABILITY_MULTIPLIERS = {
    #King's Indian Defense is a bad opening according to the internet, also Stockfish.
    #1. d4  Nf6
    #2. c4  g6
    #3. Nc3 Bg7
    #
    #3..d5 is the grunfeld which is strong
    #3..Bg7 is the KID
    ('rnbqkb1r/pppppp1p/5np1/8/2PP4/2N5/PP2PPPP/R1BQKBNR b KQkq - 0 1', 'f8g7'): 0.12,

    #KID attempt #2
    #1. d4  Nf6
    #2. c4  g6
    #3. Nf3 Bg7
    #4. Nc3 O-O
    #
    #4..d5 is grunfeld again
    #4..O-O is the KID
    ('rnbqk2r/ppppppbp/5np1/8/2PP4/2N2N2/PP2PPPP/R1BQKB1R b KQkq - 0 1', 'e8g8'): 0.12,

    #Benoni
    #1. d4  Nf6
    #2. c4  c5
    #
    #not played commonly but still a top black error in the opening
    ('rnbqkb1r/pppppppp/5n2/8/2PP4/8/PP2PPPP/RNBQKBNR b KQkq - 0 1', 'c7c5'): 0.25,

    #KID attempt #3
    #1. d4  Nf6
    #2. c4  g6
    #3. Nf3 Bg7
    #4. Nc3 d6
    #
    #4..d5 is grunfeld again
    #4..d6 is the KID
    ('rnbqk2r/ppppppbp/5np1/8/2PP4/2N2N2/PP2PPPP/R1BQKB1R b KQkq - 0 1', 'd7d6'): 0.5,

    #Winawer (French Defense)
    #1. e4  e6
    #2. d4  d5
    #3. Nc3 Bb4
    #
    #not terrible but uncommon at top levels
    ('rnbqkbnr/ppp2ppp/4p3/3p4/3PP3/2N5/PPP2PPP/R1BQKBNR b KQkq - 0 1', 'f8b4'): 0.5,

    #KID attempt #4
    #1. d4  Nf6
    #2. Nf3 g6
    #3. c4  Bg7
    #4. Nc3 O-O
    #
    #4..d5 is grunfeld
    ('rnbqk2r/ppppppbp/5np1/8/2PP4/2N2N2/PP2PPPP/R1BQKB1R b KQkq - 0 1', 'e8g8'): 0.25,

    #trap in the semi-slav! maia thinks 50/50 between f6h5 and e8g8 but in the lichess
    #masters db it's been e8g8 in all four cases, so push that down for now
    ('rn1qk2r/pb3pb1/2p1pn1p/1p2N1pB/2pPP3/2N3B1/PP3PPP/R2QK2R b KQkq - 0 1', 'f6h5'): 0.25,

    #trap in queen's indian. Maia has 15% of this game-ending blunder but probably lower than
    #that against strong competition, it's only 9% in lichess player db
    ('rn1qk2r/pb1pbppp/1pp2n2/3p1N2/2P5/6P1/PP2PPBP/RNBQK2R b KQkq - 0 1', 'd5c4'): 0.25,

    #overreacting to one time this happened in our db, vs far less common in lichess
    ('rn1qk2r/pbppbppp/1p2pn2/3P4/2P5/5NP1/PP2PPBP/RNBQK2R b KQkq - 0 1', 'c7c6'): 0.1,

    #move relatively deep in grunfeld in the default d4 book. a6 most common on lichess
    #vs b6 most common for maia and much better for white
    ('r4rk1/pp2ppbp/6p1/n2P2B1/4P3/q4P2/4BP1P/1R1QR1K1 b - - 0 1', 'a7a6'): 10,

    #another move deep in the grunfeld after a questionable b7c3 from black
    #maia has the blunder h7g6 at 75% but we see f7g6 7/7 in lichess
    ('r2qr1k1/pp3p1p/6P1/n1pPp3/4P3/2Q2P2/P3BP2/1R2K2R b K - 0 1', 'h7g6'): 0.3,

    #maia thinks 72% chance of blunder here, should be way lower
    ('1r2k2r/p2pbppp/4p3/q1p1P3/1PPn4/3Q2P1/P4PBP/1RB1R1K1 b k - 0 1', 'b8b4'): 0.05,

    #maia thinks 77% chance of blunder here, should be lower
    ('r4rk1/4Rpbp/6p1/3Pn3/p3P3/4BP2/q3BP1P/3QR1K1 b - - 0 1', 'a4a3'): 0.1,

    #maia thinks 22% chance of blunder here, should be lower
    ('r4rk1/pb3pb1/1p1qpnp1/2pP2N1/4P3/7R/P3BPP1/2BQ1RK1 w - - 0 1', 'e7e6'): 0.2,

    #maia thinks 50% chance of blunder here, should be lower
    ('1r3rk1/p4p1p/1p1P1qP1/bBp5/8/B1P5/P2Q2PP/5RK1 b - - 0 1', 'a5c3'): 5,

    #maia thinks 22% chance of blunder here, should be lower
    ('r4rk1/pb2ppb1/1p1q1np1/2pP2N1/4P3/7R/P3BPP1/2BQ1RK1 b - - 0 1', 'e7e6'): 0.25,

    #give a reasonable chance of picking the best move, we've seen f8e7 3/3
    #but lichess has seen d7d6
    ('1r1qkb1r/p2p1ppp/4p3/2p1P3/2Pn4/3Q2P1/PP3PBP/R1B1R1K1 b k - 0 1', 'd7d6'): 5,

    #maia thinks c6d4 only 10% but has happened 3/3 times in lichess
    ('r4rk1/pp2ppbp/2n3p1/3P4/4P3/4BP2/q3BP1P/1R1Q1RK1 b - - 0 1', 'c6d4'): 10,

    #would be interesting to get thoughts but maia's 10% of holding the
    #position seems low
    ('r4rk1/4Bpbp/p2P2p1/2q5/2p5/5P2/5P1P/1R1QR1K1 b - - 0 1', 'f8e8'): 5,

    #maia thinks best move is 6% likely: it's 52% in lichess db but maybe
    #that's mostly correspondence?
    ('r4rk1/pp2ppbp/6p1/n2P2B1/4P3/q4P2/4BP1P/1R1QR1K1 b - - 0 1', 'a7a6'): 10,

    #maia gives 19% chance of this move to hold, lichess has seen
    #it 1/1 times so pushing up some
    ('r4rk1/5pbp/p2P2p1/6B1/2p5/q4P2/5P1P/1R1QR1K1 b - - 0 1','a3c5'): 2,

    #stockfish misvalues position
    #even after up to 1min of evaluation (+0.91)
    #running 2min it realizes black can hold (+0.16)
    #fixed by directly editing the evals.csv file
    #'1r6/p4rkp/1p1PR3/1Bp5/8/B7/P2b2PP/6K1 w - - 0 1'

    #maia has 50/50 chance of saving position, but feels more likely
    #to me
    ('1r3k2/p4r1p/1p1P4/1Bp5/8/8/PB1bR1PP/6K1 b - - 0 1','f2g5'): 2,

    #maia has 22% chance of saving the position, feels more likely
    ('rn3rk1/pp3pp1/2p2q1p/3p4/3b2N1/1Q1BP3/PP3PPP/R4RK1 b - - 0 1','f6e6'): 3,

    #maia has 58% of this poisoned pawn blunder, feels less likely
    ('1r1qkb1r/p4ppp/3pp3/2p1P3/2Pn1B2/3Q2P1/PP3PBP/R3R1K1 b k - 0 1','b8b2'): 0.25,

    #maia has 50%, feels less likely
    ('r4rk1/3PBpbp/p5p1/2q5/8/2p2P2/5P1P/1R1QR1K1 b - - 0 1','c3c2'): 0.25,

    #mate in 3, maia has 55%
    ('r4k1r/pp3ppp/n1p2n1B/2qb4/8/5B2/PPNQ1P1P/2KRR3 b - - 0 1','d5f3'): 0.1,

    #maia has game-losing g7g8 at 25%
    ('1r6/p4rkp/1p1PR3/1Bp5/8/8/PB1b2PP/6K1 b - - 0 1','g7g8'): 0.25,

    #maia has game-losing Re7 at 49%
    ('1r3k2/p2P1r1p/1p6/1Bp3b1/8/8/PB2R1PP/6K1 b - - 0 1','f7e7'): 0.3,

    #both lose but maia has worse b8d8 at 82%
    ('1r3k2/p2Pr2p/1p6/1Bp1B1b1/8/8/P3R1PP/6K1 b - - 0 1','b8d8'): 0.1,
}

#value of studying k moves out of book
#This was originally based on a rough
#fit of 0.0036 * math.log(move_cnt + 1)
#for learning moves *in book* from the KingBase database.
#To consider: adjust so moves out of book are more effective
#and moves against stronger players should be less effective
#OUT_OF_BOOK_PREP_VALUE = lambda x: 0.0036 * math.log(x+1)
OUT_OF_BOOK_PREP_VALUE = lambda x: 0.0024 * math.log(x+1)
INCLUDE_PLACEHOLDERS = True

TEST_POSITION = None #"rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"  #"rnbqkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1"

class SuperBook:
    def __init__(self, position, starting_ev):
        self.position = position
        if self.position and self.position["val"] == TEST_POSITION:
            print("init_book: ", starting_ev)
        self.moves = {
            0: []
        }
        self.evs = {
            0: starting_ev
        }
        self.marginal_vals = {}
        self.marginal_moves = {} #{k:(added_moves, removed_moves)}
    def set_book(self, cnt, moves, ev):
        if self.position and self.position["val"] == TEST_POSITION:
            print("set_book: ", cnt, ev)
        if cnt == 0: raise
        self.moves[cnt] = moves
        # added_moves = set(moves).difference(set(self.moves[cnt-1]))
        # removed_moves = set(self.moves[cnt-1]).difference(set(moves))
        # self.marginal_moves[cnt] = (added_moves, removed_moves)
        self.evs[cnt] = ev
        
        delta = self.evs[cnt] - self.evs[cnt-1]
        if delta < -0.0001:
            #don't want this to happen: can it?
            print(self.position)
            raise
        else:
            #don't let marginal vals get too small. the algorithm
            #for picking which moves to learn is greedy, so it won't
            #be able to see past one low marginal value to the others
            val = max(delta, 0.5 * (OUT_OF_BOOK_PREP_VALUE(cnt) - OUT_OF_BOOK_PREP_VALUE(cnt-1)))
            # if cnt > 1:
            #     val = max(val, 0.9 * self.marginal_vals[cnt-1])
            self.marginal_vals[cnt] = val
    def total_moves(self):
        return max(self.moves.keys())
    def get_moves(self, k):
        return self.moves[k]
    def get_total_ev(self, k):
        return self.evs[k]
    def get_marginal_value(self, k):
        if k == 0: raise
        return self.marginal_vals[k]

class PlaceholderSuperBook(SuperBook):
    def __init__(self, position, starting_ev, N):
        self.position = position
        self.starting_ev = starting_ev
        self.N = N
        self.new_marginal_moves = []
        self.all_moves = None
    def get_moves(self, k):
        if not self.all_moves:
            self.all_moves = [(self.position["val"], f"move_{i:03}", self.get_total_ev(i)) for i in range(self.N)]
        return self.all_moves[:k]
    def get_total_ev(self, k):
        return self.starting_ev + OUT_OF_BOOK_PREP_VALUE(k)
    def get_marginal_value(self, k):
        if k == 0: raise
        return OUT_OF_BOOK_PREP_VALUE(k) - OUT_OF_BOOK_PREP_VALUE(k-1)

P1_CACHE = {}
P2_CACHE = {}
CACHE_THRESHOLD = 4
SUPERBOOK_CNT = { "unique": 0, "total": 0 }

def compute_p1_superbook(pos, cnt, optimism=0):
    if P1_CACHE.get(pos["val"],{}).get("book"):
        return P1_CACHE[pos["val"]]["book"]
    
    if len(pos["children"]) == 0:
        ev = get_ev(pos["val"], EVAL_TIME, optimism)
        if INCLUDE_PLACEHOLDERS:
            return PlaceholderSuperBook(pos, ev, cnt)
        else:
            return SuperBook(pos, ev)
    
    child_superbooks = {} #{pos: SuperBook}

    #recursively calculate best superbook for each child position
    for child in pos["children"]:
        #TODO: is -1 multiplier correct here?
        child_superbooks[child["val"]] = compute_p2_superbook(child, cnt, optimism = -1 * optimism)

    starting_ev = sum([child_superbooks[child["val"]].get_total_ev(0) * pos["probs"][child["val"]] for child in pos["children"]])

    superbook = SuperBook(pos, starting_ev)

    if pos["val"] == TEST_POSITION:
        print("compute_p1_superbook for test position")
        print("starting ev: " + str(starting_ev))
        print("child evs: ")
        for child in pos["children"]:
            print(child["val"], child_superbooks[child["val"]].get_total_ev(0))
        
    for k in range(cnt):
        best_child = max(pos["children"], key=lambda x: child_superbooks[x["val"]].get_total_ev(k))
        best_child_ev = child_superbooks[best_child["val"]].get_total_ev(k)
        best_child_book = child_superbooks[best_child["val"]]
        best_move = (pos["val"], pos["moves"][best_child["val"]], best_child_ev)

        if pos["val"] == TEST_POSITION:
            print(f"superbook with {k+1} moves: ")
            print(best_child["val"])
            print(best_child_ev)
        book_moves = set(best_child_book.get_moves(k)).union(set([best_move])) #<--- slow line here
        #TODO: marginal moves more efficient here
        superbook.set_book(k+1, book_moves, best_child_ev)

    P1_CACHE.setdefault(pos["val"],{"cnt": 0})
    global SUPERBOOK_CNT
    SUPERBOOK_CNT["total"] += 1
    if P1_CACHE[pos["val"]]["cnt"] == 0:
        SUPERBOOK_CNT["unique"] += 1
    if SUPERBOOK_CNT["total"] % 100 == 0:
        print(SUPERBOOK_CNT)
    P1_CACHE[pos["val"]]["cnt"] += 1
    if P1_CACHE[pos["val"]]["cnt"] >= CACHE_THRESHOLD:
        P1_CACHE[pos["val"]]["book"] = superbook
    return superbook

def compute_p2_superbook(pos, cnt, optimism=0):
    if P2_CACHE.get(pos["val"],{}).get("book"):
        return P2_CACHE[pos["val"]]["book"]
    
    child_superbooks = {}

    if len(pos["children"]) == 0:
        ev = 1 - get_ev(pos["val"], EVAL_TIME, -1 * optimism)
        if INCLUDE_PLACEHOLDERS:
            return PlaceholderSuperBook(pos, ev, cnt)
        else:
            return SuperBook(pos, ev)
    
    for child in pos["children"]:
        child_superbooks[child["val"]] = compute_p1_superbook(child, cnt, optimism = -1 * optimism)

    if pos["val"] == TEST_POSITION:
        print("compute_p2_superbook for test position")
        print("child evs: ")
        for child in pos["children"]:
            print(child["val"], pos["probs"][child["val"]], child_superbooks[child["val"]].get_total_ev(0))
        
    superbook = aggregate_weighted_superbooks(cnt, pos["children"], pos["probs"], child_superbooks)

    P2_CACHE.setdefault(pos["val"],{"cnt": 0})
    global SUPERBOOK_CNT
    SUPERBOOK_CNT["total"] += 1
    if P2_CACHE[pos["val"]]["cnt"] == 0:
        SUPERBOOK_CNT["unique"] += 1
    if SUPERBOOK_CNT["total"] % 100 == 0:
        print(SUPERBOOK_CNT)
    P2_CACHE[pos["val"]]["cnt"] += 1
    if P2_CACHE[pos["val"]]["cnt"] >= CACHE_THRESHOLD:
        P2_CACHE[pos["val"]]["book"] = superbook
    return superbook

def aggregate_weighted_superbooks(total_cnt, positions, probs, superbooks):
    #if you're playing black, you can build opening books against
    #c4, d4, e4, Nf3 etc
    #but how to combine those into a single opening book? probably
    #you want to include the most moves against d4 and e4 but what's
    #the exact best way to combine?

    #more generally:
    #given a list of positions, probability of reaching those positions
    #and superbooks for those positions, how to combine into an overall
    #superbook?

    cnts = {p["val"]:0 for p in positions} #pos -> number of moves from that position
    
    #compute starting ev with no opening book
    starting_ev = sum([superbooks[p["val"]].get_total_ev(0) * probs[p["val"]] for p in positions])
    output_superbook = SuperBook(None, starting_ev)

    while True:
        #Repeatedly try learning one more move from the child position with the best
        #marginal ev. Because of transpositions/overlap, incrementing that position doesn't
        #actually mean that our total opening book size increases by 1. it could increase
        #by more than 1 or even decrease

        options = [p for p in positions if cnts[p["val"]] < total_cnt]
        if not options:
            break
        best_pos = max(options, key = lambda x: superbooks[x["val"]].get_marginal_value(cnts[x["val"]]+1) * probs[x["val"]])
        cnts[best_pos["val"]] += 1
        
        all_moves = list(set([m for p in positions for m in superbooks[p["val"]].get_moves(cnts[p["val"]])]))
        ev = sum([superbooks[p["val"]].get_total_ev(cnts[p["val"]]) * probs[p["val"]] for p in positions])

        move_cnt = len(all_moves)
        last_cnt = output_superbook.total_moves()
        if move_cnt <= last_cnt:
            for i in range(move_cnt, last_cnt+1):
                output_superbook.set_book(i, all_moves, ev)
        else:
            for i in range(last_cnt+1, move_cnt+1):
                output_superbook.set_book(i, all_moves, ev)

        if move_cnt > total_cnt:
            break

        last_cnt = move_cnt
        
    return output_superbook

ENGINE = chess.engine.SimpleEngine.popen_uci("/home/jtrigg/github/stockfish/src/stockfish")
EVALS = {}

def normalize_fen(fen):
    fen = fen.split()
    fen[-1] = "1"
    fen[-2] = "0"
    fen = " ".join(fen)
    return fen

def fen_plus_move(fen, move):
    board = chess.Board(fen)
    board.push_uci(move)
    return normalize_fen(board.fen())

def load_evals():
    with open("evals.csv") as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            EVALS[row["fen"]] = (row["time"],row["move"],row["val"])

def save_evals():
    with open("evals.csv","w") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["fen","time","move","val"])
        for fen in EVALS:
            writer.writerow([fen,*EVALS[fen]])


def get_ev(fen, time, optimism=0):
    #note: evaluate_fen caches previous evaluations
    #so if the fen was evaluated more deeply in the
    #past it'll use that
    #this time is returned as eval_time
    best_move, eval_time, cp = evaluate_fen(fen, time)
    
    def sigmoid(x, L, x0, y0, k):
        y = L / (1 + math.exp(-k*(x-x0))) + y0
        return y

    def basic_sigmoid(x):
        return sigmoid(x, 1, 0, 0, 1)
    
    #centipawns to ev
    if cp == "M0":
        raise #can this happen?
    elif "-M" in str(cp):
        white_ev = 0.1
    elif "M" in str(cp):
        white_ev = 0.9
    else:
        SIGMOID_90_PERCENT = 2.19722457733
        err = 0.1 / math.log(1 + eval_time) #time in seconds
        cp = float(cp) + err * optimism
        white_ev = basic_sigmoid(SIGMOID_90_PERCENT * (cp / 10))
    
    side = fen.split()[-5]
    if side == "w":
        eval_ = white_ev
    elif side == "b":
        eval_ = 1 - white_ev
    else:
        raise
    
    return eval_

def get_eval_time(fen):
    eval_time, move, val = EVALS[fen]
    return int(eval_time)

def evaluate_fen(fen, time):
    if not EVALS:
        load_evals()
    if fen in EVALS:
        eval_time, move, val = EVALS[fen]
        if int(eval_time) >= time:
            return (move, int(eval_time), val)
    board = chess.Board(fen)
    result = ENGINE.analyse(board, chess.engine.Limit(time=time))
    score = result["score"].white()

    best_move = None
    if "pv" in result:
        best_move = str(result["pv"][0])

    if score.is_mate():
        if score.mate() >= 0:
            val = "M" + str(abs(score.mate()))
        else:
            val = "-M" + str(abs(score.mate()))
    else:
        val = score.score() / 100
    EVALS[fen] = (time, best_move, val)

    if random.random() < 0.01:
        save_evals()

        
    return best_move, time, val    

def generate_game_tree(positions):
    nodes = {}
    for fen in positions:
        nodes[fen] = {
            "val": fen
        }

    for fen in nodes:
        children = []
        moves = {}
        probs = {}

        for move in positions[fen]["probs"]:
            child_fen = fen_plus_move(fen, move)
            child_node = nodes[child_fen]

            children.append(child_node)
            moves[child_node["val"]] = move
            probs[child_node["val"]] = positions[fen]["probs"][move]
        
        nodes[fen]["children"] = children
        nodes[fen]["moves"] = moves
        nodes[fen]["probs"] = probs

    #cycle detection with dfs
    starting_fen = move_history_to_fen([])
    root_node = nodes[starting_fen]
    todos = [(root_node,[])]
    
    while todos:
        node, path = todos.pop(0)
        if node["val"] in path:
            if any([c["val"] in positions for c in node["children"]]):
                print("cycle detected: ", node["val"], path)
                raise
        else:
            for child in node["children"]:
                todos.insert(0,(child,[*path,node["val"]]))
        
    return nodes

def load_basic_positions():
    positions = {} #fen: {"wts"}
    for r in csv.DictReader(open("filtered_moves_1000.csv")):
        positions[r["fen"]] = {
            "wts": eval(r["move_cnts"]),
        }
    return positions

def load_leaves():
    leaves = [r["fen"] for r in csv.DictReader(open("leaves.csv"))]
    all_moves = {r["fen"]:eval(r["move_cnts"]) for r in csv.DictReader(open("filtered_moves_3.csv"))}
    maia_evals = {r["fen"]:eval(r["probs"]) for r in csv.DictReader(open("maia_evals.csv"))}

    positions = {} #fen: {probs}
    for fen in leaves:
        total_cnt = sum(all_moves.get(fen,{}).values())
        move_probs = {m: all_moves[fen][m]/total_cnt for m in all_moves.get(fen,{})}

        if not fen in maia_evals:
            maia_probs = fen_to_probs(fen)
            maia_evals[fen] = {x:maia_probs[x] for x in maia_probs if maia_probs[x] > 0.05}
            
        maia_probs = maia_evals[fen]
        prob_sum = sum(maia_probs.values())
        maia_normed = {x:maia_probs[x]/prob_sum for x in maia_probs}

        probs = {}
        next_moves = set([*move_probs.keys(), *maia_probs.keys()])
        for m in next_moves:
            move_wt = 0.4 * total_cnt
            maia_wt = 1
            probs[m] = (move_wt * move_probs.get(m,0) + maia_wt * maia_probs.get(m,0)) / (move_wt + maia_wt)
        positions[fen] = {
            "wts": probs,
        }

    print(f"loaded {len(positions)} leaf positions")

    with open("maia_evals.csv","w") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=["fen","probs"])
        writer.writeheader()
        for fen in leaves:
            writer.writerow({
                "fen": fen,
                "probs": maia_evals[fen]
            })

    return positions

def generate_position_stats():
    basic_positions = load_basic_positions()
    leaf_positions = load_leaves()

    input_positions = {**leaf_positions, **basic_positions} #basic_positions by default, fall back to leaf
    
    positions = {}

    for fen in input_positions:
        wts = input_positions[fen]["wts"]
        
        if fen in disallowed_moves:
            wts = {x:wts[x] for x in wts if x not in disallowed_moves.get(fen,[])}

        if fen in MISSING_MOVES:
            wts = {**wts, **MISSING_MOVES[fen]}
            
        for move in wts:
            wts[move] *= PROBABILITY_MULTIPLIERS.get((fen, move),1)
            wts[move] = wts[move] ** STRENGTH
        
        best_move = evaluate_fen(fen, EVAL_TIME)[0]
        best_move_disallowed = (best_move in disallowed_moves.get(fen,[]))
        
        if len(wts) and not best_move_disallowed:
            wts.setdefault(best_move,0)

        total_wt = sum(wts.values())
        probs = {m: wts[m]/total_wt for m in wts}

        positions[fen] = {
            "probs": probs,
        }
        
        for move in probs:
            child_fen = fen_plus_move(fen, move)
            positions.setdefault(child_fen, {
                "probs": {},
            })
    
    return positions

def move_history_to_fen(move_history):
    board = chess.Board()
    for move in move_history:
        board.push(chess.Move.from_uci(move))
    return normalize_fen(board.fen())

def generate_book(starting_fen, move_cnt, side, nodes):
    start_node = nodes[starting_fen]

    optimism = 1
    
    if side == "white":
        superbook = compute_p1_superbook(start_node, move_cnt, optimism)
    elif side == "black":
        superbook = compute_p2_superbook(start_node, move_cnt, optimism)
    else:
        raise

    #print_book(superbook, side, positions)

    #Refine evaluations:
    #initial evaluations are 1 second per move, which gives some inaccuracies
    #and the opening book will suggest some moves that look good based on 1
    #second of evaluation but wouldn't after a longer evaluation. So after computing
    #the opening book, rerun the most common positions with a longer eval (8 seconds)
    #and then rerun. Iterate as needed

    print_book(starting_fen, side, superbook, nodes)

def print_book(starting_fen, side, superbook, nodes):
    for i in range(superbook.total_moves()):
        print(i+1,superbook.get_total_ev(i+1) - superbook.get_total_ev(0))
    get_book_info(starting_fen, side, nodes, superbook, superbook.total_moves())
    print(superbook.get_moves(superbook.total_moves()))

def get_book_info(starting_fen, side, nodes, superbook, move_cnt):
    moves = superbook.get_moves(move_cnt)

    fen_to_move = {}
    for x in moves:
        fen_to_move.setdefault(x[0],[])
        fen_to_move[x[0]].append(x)
    for x in fen_to_move:
        fen_to_move[x].sort(reverse = True)
        fen_to_move[x] = fen_to_move[x][0]

    print(fen_to_move)

    #track most probable leaves
    leaves = []
    
    #track largest mistakes
    #weighted by % chance of reaching the position
    errors = []
    
    #dfs
    todos = [(nodes[starting_fen],1,[])]
    done = set()
    while todos:
        curr, prob, path = todos.pop(0)
        fen = curr["val"]
        my_turn = (side[0] == fen.split()[-5])

        if fen in fen_to_move:
            print("--")
            print(path, fen_to_move[fen])
            # print(fen_to_move[fen])
            # print("--")
            # print(chess.Board(fen))
            # print("--")
            done.add(fen)
            move = fen_to_move[fen][1]
            if "move" in move:
                leaves.append((fen, prob, path, move))
            else:
                next_fen = fen_plus_move(fen, move)
                child = [x for x in curr["children"] if x["val"] == next_fen][0]
                todos.insert(0, (child, prob, [*path, move]))
        else:
            if my_turn or (not curr["children"]):
                leaves.append((fen, prob, path))
            else:
                child_fen_to_prob = {x["val"]: curr["probs"][x["val"]] for x in curr["children"]}
                best_move = evaluate_fen(fen, EVAL_TIME)[0]
                best_move_fen = fen_plus_move(fen, best_move)
                best_move_ev = get_ev(best_move_fen, EVAL_TIME, 0)
                for x in curr["children"]:
                    move_fen = x["val"]
                    move_ev = get_ev(move_fen, EVAL_TIME, 0)
                    move_prob = child_fen_to_prob[x["val"]]
                    ev_loss = best_move_ev - move_ev

                    #adjust to skip insignificant "errors" in the first couple moves
                    adj_ev_loss = min(0,ev_loss + 0.005) 
                    errors.append((fen, move_fen, adj_ev_loss * move_prob, prob, adj_ev_loss * prob * move_prob))
                sorted_children = sorted(curr["children"], key = lambda x: child_fen_to_prob[x["val"]])
                for child in sorted_children:
                    move = curr["moves"][child["val"]]
                    todos.insert(0, (child, prob*child_fen_to_prob[child["val"]], [*path, move]))
                    
    print("---")
    print("---")
    print("top leaves")
    leaves.sort(key = lambda x: x[1], reverse=True)

    best_leaves = set([r["fen"] for r in csv.DictReader(open("leaves.csv"))])
    
    for i in leaves[:100]:
        print(i)
        fen = i[0]
        eval_time = get_eval_time(fen)
        if eval_time <= EVAL_TIME:
            #evaluate more deeply
            get_ev(fen, EVAL_TIME * 8, 0)
        else:
            #already deeply evaluated
            best_leaves.add(fen)

    print("---")
    print("---")
    print("most out of book")
    out_of_book = [l for l in leaves if len(l) == 4]
    out_of_book.sort(key = lambda x: x[3], reverse=True)

    for i in out_of_book[:100]:
        print(i)
        fen = i[0]
        eval_time = get_eval_time(fen)
        if eval_time <= EVAL_TIME:
            #evaluate more deeply
            get_ev(fen, EVAL_TIME * 8, 0)
        else:
            #already deeply evaluated
            best_leaves.add(fen)
            
    with open("leaves.csv","w") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=["fen"])
        writer.writeheader()
        for l in best_leaves:
            writer.writerow({"fen":l})
    
    print("---")
    print("---")
    print("top errors")
    errors.sort(key = lambda x: x[4])
    for i in errors[:100]:
        print(i)
        fen = i[0]
        best_move = evaluate_fen(fen, EVAL_TIME * 8)[0]
        best_move_fen = fen_plus_move(fen, best_move)
        get_ev(best_move_fen, EVAL_TIME * 8, 0)
        move_fen = i[1]
        get_ev(move_fen, EVAL_TIME * 8, 0)

    print("---")
    print("---")
    print("top blunders")
    errors.sort(key = lambda x: x[2])
    for i in errors[:100]:
        print(i)
        fen = i[0]
        best_move = evaluate_fen(fen, EVAL_TIME * 8)[0]
        best_move_fen = fen_plus_move(fen, best_move)
        get_ev(best_move_fen, EVAL_TIME * 8, 0)
        move_fen = i[1]
        get_ev(move_fen, EVAL_TIME * 8, 0)
        

if __name__ == "__main__":
    # fen = 'rnbqkb1r/pppppp1p/5np1/8/2PP4/2N5/PP2PPPP/R1BQKBNR b KQkq - 0 1'
    # print(evaluate_fen(fen, EVAL_TIME))

    positions = generate_position_stats()
    nodes = generate_game_tree(positions)

    starting_history = []

    starting_fen = move_history_to_fen(starting_history)
    print(starting_fen)
    
    move_cnt = 1000
    
    generate_book(starting_fen, move_cnt, "white", nodes)
    
    ENGINE.quit()
    save_evals()
