import chess
import chess.uci
import chess.polyglot
import chess.engine
import pickle
import csv
import math
import os.path

#Given an input of a number of games, sum across all positions
#which positions had the most "loss" (ie players lost the most EV
#in this positions)

STOCKFISH_DIR = "/home/jtrigg/install/Stockfish/src/stockfish"
INPUT_FILE = "/tmp/filtered_moves.csv"
EVAL_FILE = "/home/jtrigg/files/misc/evals.pkl"

def sigmoid(x):
  return 1 / (1 + math.exp(-x))

class Evaluator:
  def __init__(self, eval_file=None):
    super()
    self.eval_file = eval_file if eval_file else EVAL_FILE
    self.load_evals()
    self.engine = chess.uci.popen_engine(STOCKFISH_DIR)
    self.info_handler = chess.uci.InfoHandler()
    self.engine.info_handlers.append(self.info_handler)
  def evaluate_depth(self, fen, depth):
    #won't be saved
    board = chess.Board(fen)
    self.engine.position(board)
    engine_output = self.engine.go(depth=depth) # Gets a tuple of bestmove and ponder move
    score = self.info_handler.info["score"][1]
    return str(engine_output.bestmove), self.eval_to_centipawns(score.cp, score.mate)
  def evaluate_cp(self, fen, time=100, max_centipawns=10*100): #100 millis default time
    move, (cp,mate) = self.memo_eval(fen, time)
    return move, self.eval_to_centipawns(cp, mate)
  def evaluate_ev(self, fen, time=100):
    move, (cp, mate) = self.memo_eval(fen, time)
    return move, self.eval_to_ev(cp, mate)
  def memo_eval(self, fen, time=100):
    board = chess.Board(fen)
    zobrist_hash = chess.polyglot.zobrist_hash(board)

    #update
    if not zobrist_hash in self.evals:
      self.evals[zobrist_hash] = {"zobrist": zobrist_hash, "eval_time":0}

    eval_info = self.evals[zobrist_hash]

    if eval_info["eval_time"] == 0 and time <= 0:
      raise
    elif eval_info["eval_time"] == 0:
      new_time = time
      move, evaluation = self.run_eval(fen, new_time)
      eval_info["eval_time"] = new_time
      eval_info["eval"] = evaluation
      eval_info["move"] = move
    elif time > eval_info["eval_time"]:
      #round input time to a power of 2 times eval_info["eval_time"]
      new_time = eval_info["eval_time"] * 2 ** math.ceil(math.log(time/eval_info["eval_time"]) / math.log(2))
      move, evaluation = self.run_eval(fen, new_time)
      eval_info["eval_time"] = new_time
      eval_info["eval"] = evaluation
      eval_info["move"] = move
    return eval_info["move"], eval_info["eval"]
  def run_eval(self, fen, time): #time in millis
    #returns ev in terms of the side to play
    board = chess.Board(fen)
    self.engine.position(board)
    engine_output = self.engine.go(movetime=time)  # Gets a tuple of bestmove and ponder move
    score = self.info_handler.info["score"][1]
    return str(engine_output.bestmove), (score.cp, score.mate)
  def eval_to_centipawns(self, centipawns, mate):
    CAP_VAL = 10 * 100 #10+ pawns: huge advantage
    if centipawns is not None:
      centipawns = max(centipawns, -1 * CAP_VAL)
      centipawns = min(centipawns, CAP_VAL)
      return centipawns
    elif mate == 0: #you are checkmated
      return -1 * CAP_VAL
    elif mate > 0: #you have mate
      return CAP_VAL
    elif mate < 0: #you're getting mated
      return -1 * CAP_VAL
  def eval_to_ev(self, centipawns, mate):
    CAP_VAL = 10 * 100 #10+ pawns: huge advantage
    SIGMOID_90_PERCENT = 2.19722457733
    if centipawns is not None:
      centipawns = max(centipawns, -1 * CAP_VAL)
      centipawns = min(centipawns, CAP_VAL)
      return sigmoid(SIGMOID_90_PERCENT * (centipawns / CAP_VAL))
    elif mate == 0: #you are checkmated
      return 0
    elif mate > 0: #you have mate
      return 0.9
    elif mate < 0: #you're getting mated
      return 0.1
  def load_evals(self):
    #self.evals: zobrist -> {zobrist, eval_time, eval}
    if (os.path.isfile(self.eval_file)):
      self.evals = pickle.load(open(self.eval_file, "rb" ))
    else:
      self.evals = {}
  def save_evals(self):
    #print(self.evals)
    pickle.dump(self.evals, open(self.eval_file, "wb" ))


def hash_fen(fen):
  board = chess.Board(fen)
  return chess.polyglot.zobrist_hash(board)

def fen_plus_move(fen, move):
  #return fen
  board = chess.Board(fen)
  board.push(chess.Move.from_uci(move))
  return board.fen()

def move_history_to_fen(move_history):
  board = chess.Board()
  for move in eval(move_history):
    board.push(chess.Move.from_uci(move))
  return board.fen()

if __name__ == "__main__":
    ev = Evaluator()

    position_counts = {}
    #run position counts and evals
    with open(INPUT_FILE) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            zobrist_hash = hash_fen(row["start_fen"])
            position_counts[zobrist_hash] = position_counts.setdefault(zobrist_hash,0) + 1

            end_fen = fen_plus_move(row["start_fen"], row["move"])

            zobrist_hash = hash_fen(end_fen)
            position_counts[zobrist_hash] = position_counts.setdefault(zobrist_hash,0) + 1


    position_losses = {} #zobrist: {total_loss, big_loss, cnt, pgn}

    with open(INPUT_FILE) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            #TODO: compute loss as a function of the eval of the best possible move

            start_fen = row["start_fen"]
            end_fen = fen_plus_move(row["start_fen"], row["move"])

            #print(start_fen)

            #TODO? change eval time based on poscnt?
            poscnt = position_counts[hash_fen(start_fen)]
            poscnt = position_counts[hash_fen(end_fen)]

            #optional speedup: skip rare moves?
            move, _ = ev.evaluate(start_fen,100)
            best_move_fen = fen_plus_move(start_fen, move)

            best_move_ev = 1 - ev.evaluate(best_move_fen,100)[1]
            end_ev = 1 - ev.evaluate(end_fen,100)[1]
            loss = best_move_ev - end_ev

            if (loss > 0.05 or loss < 0): #approx 1 pawn
              #recompute with longer eval
              move, _ = ev.evaluate(start_fen,1000)
              best_move_fen = fen_plus_move(start_fen, str(move))

              best_move_ev = 1 - ev.evaluate(best_move_fen,1000)[1]
              end_ev = 1 - ev.evaluate(end_fen,1000)[1]
              loss = best_move_ev - end_ev

            board = chess.Board(start_fen)
            zobrist_hash = chess.polyglot.zobrist_hash(board)
            default = {"total_loss":0, "big_loss": 0, "cnt":0, "pgn":row["start_fen"], "previous_moves":row["previous_moves"]}
            position_losses.setdefault(zobrist_hash,default)
            position_losses[zobrist_hash]["cnt"] += 1
            position_losses[zobrist_hash]["total_loss"] += loss
            #losses in excess of 5% ev (~= one pawn)
            position_losses[zobrist_hash]["big_loss"] += max(0,loss-0.05)

            move_info = position_losses[zobrist_hash].setdefault("moves",{})
            move_info[row["move"]]["cnt"] = move_info.setdefault(row["move"],{"loss":loss, "cnt":0})["cnt"] + 1
            #print(move_info)
    positions = sorted(list(position_losses.items()), key = lambda x: x[1]["total_loss"], reverse=True)

    for p in positions[:100]:
        #filter for top responses
        info = p[1]
        moves1 = sorted(info["moves"].items(), key = lambda x: x[1]["cnt"] * x[1]["loss"], reverse=True)[:2]
        moves2 = sorted(info["moves"].items(), key = lambda x: x[1]["cnt"], reverse=True)[:2]
        moves3 = sorted(info["moves"].items(), key = lambda x: x[1]["cnt"] * max(x[1]["loss"]-0.05,0), reverse=True)[:2]
        pgns = list(set([i[0] for l in [moves1, moves2, moves3] for i in l])) #flatten
        moves = [x for x in info["moves"].items() if x[0] in pgns]

        #print position summary
        print((eval(p[1]["previous_moves"]),{k: p[1][k] for k in ['total_loss', 'big_loss', 'cnt']}))

        #print responses
        for m in moves:
          print(m)
        print('\n')
    ev.save_evals()
