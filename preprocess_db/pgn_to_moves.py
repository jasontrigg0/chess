#https://github.com/niklasf/python-chess
import chess
import chess.uci
import chess.pgn
import chess.polyglot
import csv
import random

import hashlib
import math
import base64

from eval_moves import fen_plus_move, move_history_to_fen

#TODO: lots of unused code here, try to remove it
#Read in a pgn list of games and generate a csv of moves

#PGN_FILE = "/ssd/files/chess/lichess_db_standard_rated_2018-10.pgn"
PGN_FILE = "/home/jtrigg/files/misc/KingBase2018-all.pgn"
#PGN_FILE = "/tmp/test.pgn"
#PGN_FILE = "/tmp/kingbase1pct.pgn"
CEREBELLUM_FILE = "/home/jtrigg/Downloads/Cerebellum_light_180611/Cerebellum_Light_Poly.bin"

MAX_GAME_CNT = 100000000
GAME_FRAC = 1 #0.03 TODO: think this is being used in two places right now, should be fixed before using
MOVE_FRAC = 1 #0.03


FILTER_MIN_CNT = 20 #None
PARALLEL_TOTAL = 10 # PARALLEL_TOTAL times, each
PARALLEL_ID = None #seed takes on values in range(PARALLEL_TOTAL)

class Game():
    def __init__(self, game):
        self.game = game
    def headers(self):
        return self.game.headers
    def result(self):
        return {
            "0-1": 0,
            "1/2-1/2":0.5,
            "1-0":1,
            "*":None
        }[self.game.headers["Result"]]
    def moves(self):
        board = self.game.board()
        move_history = []
        for move in self.game.mainline_moves():
            start_position = board.fen()
            info = {"white_elo": self.game.headers["WhiteElo"], "black_elo": self.game.headers["BlackElo"], "result": self.game.headers["Result"], "move_history": str(move_history), "turn": 1 if board.turn else -1, "fen":start_position, "move":str(move)}
            if random.random() < MOVE_FRAC:
                yield info
            #update with new move
            board.push(move)
            move_history.append(str(move))
    def __str__(self):
        return str(self.game)

def pgn_to_games(pgn_file=PGN_FILE, high_elo=False):
    pgn = open(pgn_file, errors="replace")
    for i in range(MAX_GAME_CNT):
        game = chess.pgn.read_game(pgn)
        if not game:
            break
        # if high_elo and not (int(game.headers["WhiteElo"]) > 2600 or int(game.headers["BlackElo"]) > 2600):
        #    continue
        # event_name = game.headers["Event"].lower()
        # if "rapid" in event_name or "blitz" in event_name or "speed" in event_name:
        #     continue
        if random.random() > GAME_FRAC: #skip the game
            continue
        yield Game(game)

def pgn_to_games_parallel(pgn_file=PGN_FILE, high_elo=False, parallel_cnt=1, parallel_id=None):
    #read through fast getting all the relevant games
    pgn = open(pgn_file, errors="replace")
    offsets = []
    cnt = 0
    while True:
        offset = pgn.tell()
        cnt += 1
        if cnt % 10000 == 0: print(cnt)
        headers = chess.pgn.read_headers(pgn)
        if headers is None:
            break
        eco = headers["ECO"]
        if hash_to_bin(eco, parallel_cnt) == parallel_id:
            offsets.append(offset)
    print("here")
    for offset in offsets:
        pgn.seek(offset)
        game =chess.pgn.read_game(pgn)
        if random.random() > GAME_FRAC:
            continue
        yield Game(game)

def basic_hash(x):
    return hashlib.md5(x.encode("UTF-8"))

def hash_to_float(x):
    return int(basic_hash(x).hexdigest(), 16) % (10 ** 8) / (10 ** 8)

def hash_to_bin(x, N):
    #assign to one of N bins (0,1,..N-1)
    return math.floor(hash_to_float(x) * N)

#deprecated
def fetch_games_parallel(parallel_total, parallel_id):
    #100 games -> 6620 distinct positions
    #1000 games -> 64012 distinct positions
    #10000 games -> 610650 distinct positions
    if FILTER_MIN_CNT:
        seeds_to_run = [PARALLEL_ID] if (PARALLEL_ID is not None) else range(PARALLEL_TOTAL)
        for seed in seeds_to_run:
            cnts = {}
            game_cnt = 0
            for game in pgn_to_games(PGN_FILE):
                game_cnt += 1
                if (game_cnt % 100 == 0): print(game_cnt)
                for move in game.moves():
                    if (hash_to_bin(move["move_history"],PARALLEL_TOTAL) == seed):
                        basic_hash_val = basic_hash(move["move_history"]).digest()
                        cnts[basic_hash_val] = cnts.setdefault(basic_hash_val,0) + 1
            for game in pgn_to_games(PGN_FILE):
                for move in game.moves():
                    if (hash_to_bin(move["move_history"],PARALLEL_TOTAL) == seed):
                        basic_hash_val = basic_hash(move["move_history"]).digest()
                        if cnts[basic_hash_val] >= FILTER_MIN_CNT:
                            outrow = {"start_fen":move["fen"], "move_history":move["move_history"], "move":move["move"]}
                            writer.writerow(outrow)

def pgn_to_csv():
    with open("/ssd/files/chess/games.csv",'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["moves"])
        for game in pgn_to_games(PGN_FILE):
            moves = [m["move"] for m in game.moves()]
            if moves[0] == "c7c5": continue #skip weird game from kingbase that starts with first move "c7c5" (??)
            writer.writerow([moves])

def game_moves_to_fens(moves):
    fen = move_history_to_fen(str([]))
    for i in range(len(moves)):
        history = str(moves[:i])
        next_move = moves[i]
        yield fen
        #update fen to include the next move
        fen = fen_plus_move(fen, moves[i])

def drop_fen_50_moves(fen):
    pieces = fen.split()
    pieces[-2] = "-"
    return " ".join(pieces)

def filter_csv():
    # with open("/ssd/files/chess/game_fens.csv", 'w') as outfile:
    #     writer = csv.writer(outfile)
    #     writer.writerow(["fens"])
    #     with open("/ssd/files/chess/games.csv") as csvfile:
    #         reader = csv.reader(csvfile)
    #         cnt = 0
    #         for r in reader:
    #             if r[0] == "moves": continue #header
    #             cnt += 1
    #             if (cnt % 1000 == 0): print(cnt)
    #             moves = eval(r[0])
    #             fens = [fen for fen in game_moves_to_fens(moves)]
    #             writer.writerow([fens])

    with open("/ssd/files/chess/filtered_moves_20200309.csv", 'w') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(["fen","move_cnts","move_history"])
        for seed in range(PARALLEL_TOTAL):
            fen_cnts = {}
            with open("/ssd/files/chess/games.csv") as csvfile:
                with open("/ssd/files/chess/game_fens.csv") as fenfile:
                    game_reader = csv.reader(csvfile)
                    fen_reader = csv.reader(fenfile)
                    game_cnt = 0
                    for game_row, fen_row in zip(game_reader, fen_reader):
                        if game_row[0] == "moves": continue #header
                        game_cnt += 1
                        if (game_cnt % 1000 == 0):
                            print(game_cnt)
                        moves = eval(game_row[0])
                        fens = eval(fen_row[0])
                        if len(moves) != len(fens):
                            raise
                        for i in range(len(moves)):
                            fen = fens[i]
                            fen = drop_fen_50_moves(fen)
                            if hash_to_bin(fen,PARALLEL_TOTAL) == seed:
                                fen_cnts[fen] = fen_cnts.setdefault(fen,0) + 1
            positions = {}
            with open("/ssd/files/chess/games.csv") as csvfile:
                with open("/ssd/files/chess/game_fens.csv") as fenfile:
                    game_reader = csv.reader(csvfile)
                    fen_reader = csv.reader(fenfile)
                    game_cnt = 0
                    for game_row, fen_row in zip(game_reader, fen_reader):
                        if game_row[0] == "moves": continue #header
                        game_cnt += 1
                        if (game_cnt % 1000 == 0):
                            print(game_cnt)
                        moves = eval(game_row[0])
                        fens = eval(fen_row[0])
                        if len(moves) != len(fens):
                            raise
                        for i in range(len(moves)):
                            history = str(moves[:i])
                            next_move = moves[i]
                            fen = fens[i]
                            fen = drop_fen_50_moves(fen)
                            if fen in fen_cnts and fen_cnts[fen] >= FILTER_MIN_CNT:
                                default = {"fen": fen, "move_cnts":{}, "move_history":history}
                                info = positions.setdefault(fen,default)
                                info["move_cnts"][next_move] = info["move_cnts"].setdefault(next_move,0) + 1

            for fen in positions:
                if sum(positions[fen]["move_cnts"].values()) >= FILTER_MIN_CNT:
                    info = positions[fen]
                    writer.writerow([fen, str(info["move_cnts"]), info["move_history"]])
            # with open("/tmp/games.csv") as csvfile:
            #     #set "probs":{},
            #     reader = csv.reader(csvfile)
            #     for r in reader:
            #         moves = eval(r[0])
            #         if r[0] == "moves": continue
            #         for i in range(len(moves)):
            #             history = moves[:i]
            #             next_move = moves[i]
            #             if (hash_to_bin(str(history),PARALLEL_TOTAL) == seed):
            #                 basic_hash_val = basic_hash(str(history)).digest()
            #                 if positions[basic_hash_val] >= FILTER_MIN_CNT:
            #                     writer.writerow([history,next_move])


if __name__ == "__main__":
    #OUTPUT_FILE = "/tmp/filtered_moves.csv" if FILTER_MIN_CNT else "/tmp/moves.csv"

    #pgn_to_csv()
    filter_csv()
