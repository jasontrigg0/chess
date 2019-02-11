from compute_features import compute_all_features
from pgn_to_moves import pgn_to_games
import chess
import chess.pgn
import csv
import argparse
import sys

#OUTPUT_FILE="/tmp/best_games.csv"

def readCL():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f','--infile')
    args = parser.parse_args()
    return args

def compute_move_score(features, baseline_elo = None):
    r = features
    #move scores computed from regressions
    #on the outputs of compute_features.py
    #see snakefile for details
    loss_score = 2340.9681461323244 \
                 -0.18393455770905523 * float(r["loss"]) \
                 +6.897182345615584e-08 * (abs(float(r["eval"]))**2) * float(r["loss"]) \
                 -0.00028345235745415916 * float(r["loss"]) * float(r["loss_8"]) \
                 +0.00010261955601178737 * float(r["loss"])**2

    if baseline_elo is None:
        baseline_elo = 2338.0550526358907

    expected_loss_score = 2331.964433548663 \
                          -0.002847156641197759 * abs(float(r["eval"])) \
                          +0.0028983736682775423 * baseline_elo \
                          -0.020324059440379193 * float(r["loss_0"]) \
                          -0.010478102971850142 * float(r["loss_1"]) \
                          -0.008222595091880787 * float(r["loss_2"]) \
                          -0.005953224272640579 * float(r["loss_4"]) \
                          -0.0358698323455141 * float(r["loss_8"])
    pred_variance = 46.20473471437775 + 0.19409407391742095 * abs(float(r["eval"]))
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

            #print(move["fen"],move["move"],move_score,features["eval"], features["loss"])

            if move["turn"] == "white":
                move_scores["white"].append(move_score)
                move_scores_2600["white"].append(move_score_2600)
                move_scores_2800["white"].append(move_score_2800)
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
