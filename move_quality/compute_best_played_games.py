from compute_features import compute_all_features
from pgn_to_moves import pgn_to_games
import chess
import chess.pgn
import csv
import argparse
import sys

def readCL():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f','--infile')
    parser.add_argument('-v','--verbose', action="store_true")
    args = parser.parse_args()
    return args

def compute_move_score(features, baseline_elo = None):
    r = features
    #move scores computed from regressions
    #on the outputs of compute_features.py
    #see snakefile for details

    #coeffs from (100milli? 250milli?) dataset
    #Rsq elo ~ loss_score: O(0.0054120139243838405) without eval terms
    # 0.02275779946229073 with eval terms
    loss_score = 2343.5695349784564 \
                 +0.17328750070679305 * float(r["eval"]) \
                 -0.00014392142783538066 * float(r["eval"]) * abs(float(r["eval"])) \
                 -0.28213947008949963 * float(r["loss"]) \
                 +0.0001550923020553411 * abs(float(r["eval"])) * float(r["loss"]) \
                 +0.00023492720062577783 * float(r["loss"])**2 \
                 -1.6241708803212144e-07 * float(r["eval"]) * (float(r["loss"])**2) \
                 -0.0005213211696052238 * float(r["loss"]) * float(r["loss_8"])

    if baseline_elo is None:
        baseline_elo = 2338.0550526358907

    #Rsq 0.1371735633833867 without eval terms
    #
    expected_loss_score = 2330.6097157975482 \
                          +0.1666545730570659 * float(r["eval"]) \
                          -0.00013908391541252887 * float(r["eval"]) * abs(float(r["eval"])) \
                          -0.0029673935017738673 * abs(float(r["eval"])) \
                          +4.6556389612952405 * (abs(float(r["eval"])) == 1000) \
                          +0.004233935191547974 * baseline_elo \
                          -0.033021718253851265 * float(r["loss_0"]) \
                          -0.008957125716441413 * float(r["loss_1"]) \
                          -0.008578359135434978 * float(r["loss_2"]) \
                          -0.007296197013745937 * float(r["loss_4"]) \
                          -0.05257338584086794 * float(r["loss_8"]) \
                          -0.003535623029515085 * abs(float(r["king_danger"]))
    pred_variance = 86.95529115433591 + 0.1428141737036239 * abs(float(r["eval"]))
    move_score = (loss_score - expected_loss_score) / pred_variance

    return move_score

if __name__ == "__main__":
    args = readCL()

    fieldnames = ["event", "round", "white", "black", "player", "avg_score", "total_score_2600", "total_score_2800"]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for game in pgn_to_games(args.infile, high_elo=True):
        move_scores = {"white":[], "black":[]}
        move_scores_2600 = {"white":[], "black":[]}
        move_scores_2800 = {"white":[], "black":[]}

        #print(game.headers())
        for move in game.moves():
            features = compute_all_features(move["fen"], move["move"])
            move_score = compute_move_score(features)
            move_score_2600 = compute_move_score(features, 2600)
            move_score_2800 = compute_move_score(features, 2800)
            if (args.verbose):
                print(move_score, move_score_2600, move_score_2800)
                print(features)
                print(move["fen"],move["move"],move_score,features["eval"], features["loss"])

            if move["turn"] == 1:
                move_scores["white"].append(move_score)
                move_scores_2600["white"].append(move_score_2600)
                move_scores_2800["white"].append(move_score_2800)

                # print(move["fen"], move["move"])
                # print(features["eval"])
                # print(features["loss"])
                # print(features["loss_8"])
                # print(move_score,move_score_2600,move_score_2800)
            else:
                move_scores["black"].append(move_score)
                move_scores_2600["black"].append(move_score_2600)
                move_scores_2800["black"].append(move_score_2800)

        info = {
            "event": game.headers()["Event"],
            "round": game.headers()["Round"],
            "white": game.headers()["White"],
            "black": game.headers()["Black"],
        }

        avg_score_white = sum(move_scores["white"]) / len(move_scores["white"])
        avg_score_black = sum(move_scores["black"]) / len(move_scores["black"])

        total_score_2600_white = sum(move_scores_2600["white"])
        total_score_2600_black = sum(move_scores_2600["black"])

        total_score_2800_white = sum(move_scores_2800["white"])
        total_score_2800_black = sum(move_scores_2800["black"])

        info_white = {
            **info,
            "player":game.headers()["White"],
            "avg_score": avg_score_white,
            "total_score_2600": total_score_2600_white,
            "total_score_2800": total_score_2800_white
        }

        info_black = {
            **info,
            "player":game.headers()["Black"],
            "avg_score": avg_score_black,
            "total_score_2600": total_score_2600_black,
            "total_score_2800": total_score_2800_black
        }

        writer.writerow(info_white)
        writer.writerow(info_black)
        sys.stdout.flush()
