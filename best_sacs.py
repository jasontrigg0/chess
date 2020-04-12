from pgn_to_moves import pgn_to_games
import argparse
from compute_features import get_stockfish_features, get_material_difference
import csv
import sys
from eval_moves import Evaluator

ev = Evaluator()

def readCL():
    parser = argparse.ArgumentParser()
    parser.add_argument("-f","--infile")
    parser.add_argument("--print_best",action="store_true",help="print pgn of best sac games")
    parser.add_argument("-v","--verbose",action="store_true")
    args = parser.parse_args()
    return args

def get_game_info(game, verbose):
    sac_score = 0
    for move in game.moves():
        #sacs are scored as follows:
        #a player scores points when the opponent has a turn with more material than you
        #scored in proportion to material deficit squared
        #of course, you must win in the end to earn the points
        material_difference = (get_material_difference(move["fen"]))
        #print(material_difference)
        if move["turn"] != game.result(): #loser to move
            if (material_difference > 0):
                sac_score += material_difference ** 2

        if verbose:
            print(material_difference)

    m, final_eval = ev.evaluate_cp(move["fen"],1000) #from perspective of the player to play
    final_eval *= move["turn"] #from white's perspective

    info = {
        "event": game.headers()["Event"],
        "round": game.headers()["Round"],
        "white": game.headers()["White"],
        "black": game.headers()["Black"],
        "result": game.result(),
        "final_eval": final_eval,
        "sac_score": sac_score
    }
    return info

if __name__ == "__main__":
    args = readCL()
    fieldnames = ["event", "round", "white", "black", "result", "sac_score", "final_eval"]
    if args.print_best:
        fieldnames += ["pgn"]

    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for game in pgn_to_games(args.infile, high_elo=True):
        if (game.result() in [0.5,None]): continue

        info = get_game_info(game, args.verbose)

        if args.print_best:
            if info["sac_score"] > 10 * 1000 * 1000:
                info["pgn"] = str(game)
                writer.writerow(info)
        else:
            writer.writerow(info)

        sys.stdout.flush()
