#https://github.com/niklasf/python-chess
import chess
import chess.uci
import chess.pgn
import chess.polyglot
import csv
import random

#Read in a pgn list of games and generate a csv of moves

#PGN_FILE = "/home/jtrigg/Downloads/lichess_db_standard_rated_2018-10.pgn"
PGN_FILE = "/home/jtrigg/files/misc/KingBase2018-all.pgn"
#PGN_FILE = "/tmp/kingbase1pct.pgn"
CEREBELLUM_FILE = "/home/jtrigg/Downloads/Cerebellum_light_180611/Cerebellum_Light_Poly.bin"

MAX_GAME_CNT = 10000000
GAME_FRAC = 1 #0.03
MOVE_FRAC = 1 #0.03

class Game():
    def __init__(self, game):
        self.game = game
    def headers(self):
        return self.game.headers
    def moves(self):
        board = self.game.board()
        move_history = []
        for move in self.game.mainline_moves():
            start_position = board.fen()
            info = {"white_elo": self.game.headers["WhiteElo"], "black_elo": self.game.headers["BlackElo"], "result": self.game.headers["Result"], "move_history": str(move_history), "turn": "white" if board.turn else "black", "fen":start_position, "move":str(move)}
            if random.random() < MOVE_FRAC:
                yield info
            #update with new move
            board.push(move)
            move_history.append(str(move))

def pgn_to_games(pgn_file=PGN_FILE, high_elo=False):
    pgn = open(pgn_file, errors="replace")
    for i in range(MAX_GAME_CNT):
        game = chess.pgn.read_game(pgn)
        if not game:
            break
        if high_elo and not (int(game.headers["WhiteElo"]) > 2600 or int(game.headers["BlackElo"]) > 2600):
           continue
        event_name = game.headers["Event"].lower()
        if "rapid" in event_name or "blitz" in event_name or "speed" in event_name:
            continue
        if random.random() > GAME_FRAC: #skip the game
            continue
        yield Game(game)

if __name__ == "__main__":
    OUTPUT_FILE = "/tmp/moves_test.csv"
    with open(OUTPUT_FILE, 'w') as csvfile:
        fieldnames = ["white_elo", "black_elo", "result", "fen", "move_history", "move"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        #100 games -> 6620 distinct positions
        #1000 games -> 64012 distinct positions
        #10000 games -> 610650 distinct positions
        for game in pgn_to_games(PGN_FILE):
            for move in game.moves():
                outrow = {x:move[x] for x in fieldnames}
                writer.writerow(outrow)

    # not using cerebellum at the moment:

    # board = chess.Board()
    # with chess.polyglot.open_reader(CEREBELLUM_FILE) as reader:
    #     for entry in reader.find_all(board):
    #         print(dir(entry))
    #         print(entry.move(), entry.weight, entry.learn)
