#some interesting predictions:
#predict centipawn loss from a given position
#predict move from (elo, position)
#predict elo from move in a position
#predict draw chance, expected_value from elos + position
import csv
from eval_moves import Evaluator, fen_plus_move
import chess
import subprocess
import json
import sys

ev = Evaluator()

INPUT_FILE = "/tmp/pred_data.csv"
OUTPUT_FILE = "/tmp/test.csv" #chess_features.csv"

#loss feature
def compute_loss(fen, move, eval_time_millis = 100):
    #returns eval, loss
    best_move, _ = ev.evaluate_cp(fen, eval_time_millis) #TODO: maybe should return this eval instead of throwing it away and using "best_eval" below, which is from the other player's perspective
    best_move_fen = fen_plus_move(fen, best_move)
    _, best_eval = ev.evaluate_cp(best_move_fen, eval_time_millis)

    observed_move_fen = fen_plus_move(fen,move)
    _, observed_eval = ev.evaluate_cp(observed_move_fen, eval_time_millis)

    #-1 to flip to the perspective of the player currently to play
    return -1 * best_eval, -1 * (best_eval - observed_eval)


#TODO: previously was computing each eval only once
#now rerun feature generation and regressions with this
#averaging depth0 + depth1 10x each to see if it helps
EVAL_DEPTHS = [{"depth": 0, "cnt":10},
               {"depth": 1, "cnt":10},
               {"depth": 2, "cnt":1},
               {"depth": 4, "cnt":1},
               {"depth": 8, "cnt":1}];

def compute_all_features(position, move):
    TIME_MILLIS = 100 #maybe increase for more stability? not sure
    features = {}
    eval_, loss = compute_loss(position, move, TIME_MILLIS)
    features["eval"] = eval_
    features["loss"] = loss

    for depth_info in EVAL_DEPTHS:
        #lower depths are noisy, so compute them multiple times and average
        total_loss = 0
        for i in range(depth_info["cnt"]):
            best_move_at_depth, _ = ev.evaluate_depth(position,depth_info["depth"])
            _, loss = compute_loss(position, best_move_at_depth, TIME_MILLIS)
            total_loss += loss
        features["loss_"+str(depth_info["depth"])] = total_loss / depth_info["cnt"]

    stockfish_features = get_stockfish_features(position)

    features["phase"] = stockfish_features['other_features']['phase']
    features['scale_factor'] = stockfish_features['other_features']['scale_factor']
    features['static_eval'] = stockfish_features['eval_features']['total']
    features['king_danger'] = stockfish_features['eval_features']['king_danger']
    features["opening"] = 1*(float(position.split()[-1]) < 10)
    return features

def get_stockfish_features(position):
    #TODO: all features are from white perspective, need to flip to the perspective of the side to play
    output = subprocess.run(['node', 'stockfish_features.js',position],stdout=subprocess.PIPE).stdout
    feature_obj = json.loads(output)

    #stockfish features are from white's perspective
    #adjust for side to play
    turn = get_turn(position)
    for k in feature_obj['eval_features']:
        feature_obj['eval_features'][k] *= turn

    return feature_obj

def get_material_difference(position):
    #to compute faster than running the stockfish features
    board = chess.Board(position)
    diff = 208 * (len(list(board.pieces(1,True))) - len(list(board.pieces(1,False)))) + \
           865 * (len(list(board.pieces(2,True))) - len(list(board.pieces(2,False)))) + \
           918 * (len(list(board.pieces(3,True))) - len(list(board.pieces(3,False)))) + \
           1378 * (len(list(board.pieces(4,True))) - len(list(board.pieces(4,False)))) + \
           2687 * (len(list(board.pieces(5,True))) - len(list(board.pieces(5,False))))
    return diff * get_turn(position)

def get_turn(position):
    return 1 if position.split()[1] == 'w' else -1

if __name__ == "__main__":
    input_field_names = ['position','move','elo', 'opp_elo','result']
    output_field_names = input_field_names + ['eval', 'loss', 'phase', 'king_danger', 'opening', 'static_eval', 'scale_factor']

    output_field_names += ['loss_'+str(i) for i in EVAL_DEPTHS]

    writer = csv.DictWriter(sys.stdout, fieldnames = output_field_names)
    writer.writeheader()

    with open(INPUT_FILE) as fin:
        reader = csv.DictReader(fin)
        for input_row in reader:
            features = compute_all_features(input_row["position"], input_row["move"])
            writer.writerow({**features, **input_row})
