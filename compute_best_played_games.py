from eval_moves import Evaluator
from compute_loss_data import compute_loss
from pgn_to_moves import pgn_to_games
import chess
import chess.pgn
import csv

if __name__ == "__main__":
    fieldnames = ["event", "round", "white", "black", "player", "avg_loss"]
    writer = csv.DictWriter(open("/tmp/best_games.csv",'w'), fieldnames=fieldnames)
    writer.writeheader()
    for game in pgn_to_games():
        losses = {"white":[], "black":[]}
        print(game.headers())
        for move in game.moves():
            _, loss = compute_loss(move["fen"], move["move"], 100)

            if move["turn"] == "white":
                losses["white"].append(loss)
            else:
                losses["black"].append(loss)

        info = {
            "event": game.headers()["Event"],
            "round": game.headers()["Round"],
            "white": game.headers()["White"],
            "black": game.headers()["Black"],
        }

        info_white = {**info, **{"player":game.headers()["White"], "avg_loss": sum(losses["white"]) / len(losses["white"])}}
        info_black = {**info, **{"player":game.headers()["Black"], "avg_loss": sum(losses["black"]) / len(losses["black"])}}

        writer.writerow(info_white)
        writer.writerow(info_black)
