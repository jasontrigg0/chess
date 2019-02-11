#some interesting predictions:
#predict centipawn loss from a given position
#predict move from (elo, position)
#predict elo from move in a position
#predict draw chance, expected_value from elos + position
import csv
from eval_moves import Evaluator, fen_plus_move

ev = Evaluator()

INPUT_FILE = "/tmp/pred_data.csv"
OUTPUT_FILE = "/tmp/chess_features.csv"

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


EVAL_DEPTHS = [0,1,2,4,8]

def compute_all_features(position, move):
    features = {}
    eval_, loss = compute_loss(position, move, 100)
    features["eval"] = eval_
    features["loss"] = loss

    for depth in EVAL_DEPTHS:
        best_move_at_depth, _ = ev.evaluate_depth(position,depth)
        _, features["loss_"+str(depth)] = compute_loss(position, best_move_at_depth, 100)
    return features


if __name__ == "__main__":
    fout = open(OUTPUT_FILE,'w')
    input_field_names = ['position','move','elo', 'opp_elo','result']
    output_field_names = input_field_names + ['eval', 'loss']

    output_field_names += ['loss_'+str(i) for i in EVAL_DEPTHS]

    writer = csv.DictWriter(fout, fieldnames = output_field_names)
    writer.writeheader()

    with open(INPUT_FILE) as fin:
        reader = csv.DictReader(fin)
        for input_row in reader:
            features = compute_all_features(input_row["position"], input_row["move"])
            writer.writerow({**features, **input_row})
