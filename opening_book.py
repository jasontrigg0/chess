#compute the best opening book given
#given and a maximum number of moves to remember
#computes the most effective positions to memorize
#this works by taking in a list of real game positions
#(at least 20 instances of each position), together with
#the played responses to give a sense for how humans
#play out a position instead of relying entirely
#on stockfish evals

from eval_moves import Evaluator, hash_fen, fen_plus_move, move_history_to_fen
import csv
from jtutils import pairwise

#read the graph of positions, along with the ev
EVALUATOR = Evaluator()

INPUT_FILE = "/tmp/filtered_moves.csv"
EVAL_TIME = 1000

#TODO: create opening book class
# and complete opening book (for i from 1-N, contains all best opening books with <=i moves)

#INCLUDED IN SuperBook -- need to delete
# def generate_marginal_evs(starting_ev, info):
#     if not info: return
#     info[0]["marginal_ev"] = info[0]["total_ev"] - starting_ev
#     for x1,x2 in pairwise(info):
#         x2["marginal_ev"] = x2["total_ev"] - x1["total_ev"]

def compute_p1_book(pos, prev_moves, n):
    #return the n moves to memorize that will give the greatest advantage
    #along with the value for memorizing the first k for k in [0,1,...n]

    #MUST: replace "info" with "subbooks"
    if pos.is_leaf():
        return SuperBook(pos, pos.get_ev())

    superbooks = {} #{node: SuperBook}

    #step 1: compute book for each child node
    for child in pos.children:
        superbooks[child] = compute_p2_book(child, prev_moves[:] + [pos.moves[child]], n)

    #now the real computation
    starting_ev = sum([superbooks[child].get_starting_ev() * pos.probs[child] for child in pos.children])

    #step 2: if we don't include this position in the book
    #        assume we play randomly according to pos.probs
    #        and compute the optimal opening book
    skip_superbook = aggregate_random_books(n, pos.children, pos.probs, superbooks)

    #step 3: if we do include this position in the book
    choose_superbook = SuperBook(pos, starting_ev)
    for k in range(n): #compute books with 0 to n-1 moves from the children
        #list of positions with at least k moves to learn
        #TODO: it may be the case that the best position has only m << n moves in its book
        #      then when we're iterating through m+1, m+2, ... n-1 moves we'll choose suboptimal
        #      positions if they have enough moves.
        #      maybe the subbook should store the best book with <= i moves instead of the best
        #      book with exactly i moves? not sure
        options = [c for c in pos.children if superbooks[c].get_size() >= k]
        if len(options) == 0: continue

        def get_total_ev(x):
            if k == 0:
                return superbooks[x].get_starting_ev()
            else:
                return superbooks[x].get_total_ev(k)
        best_child = max(options, key=get_total_ev)
        best_total_ev = get_total_ev(best_child)

        total_ev = best_total_ev
        if k == 0:
            moves = [(prev_moves,pos.moves[best_child],total_ev)] #TODO: is total_ev necessarily the max ev? or does it include "oversized" books?
        else:
            moves = superbooks[best_child].get_book(k).moves + [(prev_moves,pos.moves[best_child],total_ev)]
        assert(k+1 == len(moves))
        choose_superbook.add_book(k+1, moves, total_ev)

    #step 4: combine info_1 (best books if we exclude the current position)
    #and info_2 (best books if we do include the currect position)
    superbook = SuperBook(pos, starting_ev)
    info = []
    for k in range(n):
        if skip_superbook.get_size() >= k+1 and choose_superbook.get_size() >= k+1:
            skip_ev = skip_superbook.get_total_ev(k+1)
            choose_ev = choose_superbook.get_total_ev(k+1)
            skip_book = skip_superbook.get_book(k+1)
            choose_book = choose_superbook.get_book(k+1)
            if skip_ev > choose_ev:
                assert(k+1 == len(skip_book.moves))
                superbook.add_book(k+1, skip_book.moves, skip_ev)
            else:
                assert(k+1 == len(choose_book.moves))
                superbook.add_book(k+1, choose_book.moves, choose_ev)
        elif skip_superbook.get_size() >= k+1:
            skip_ev = skip_superbook.get_total_ev(k+1)
            skip_book = skip_superbook.get_book(k+1)
            assert(k+1 == len(skip_book.moves))
            superbook.add_book(k+1, skip_book.moves, skip_ev)
        elif choose_superbook.get_size() >= k+1:
            choose_ev = choose_superbook.get_total_ev(k+1)
            choose_book = choose_superbook.get_book(k+1)
            assert(k+1 == len(choose_book.moves))
            superbook.add_book(k+1, choose_book.moves, choose_ev)

    return superbook

def compute_p2_book(pos, prev_moves, n):
    #compute the book for a node which is the opponent's turn
    if pos.is_leaf():
        return SuperBook(pos, 1 - pos.get_ev())

    superbooks = {}
    for child in pos.children:
        superbooks[child] = compute_p1_book(child, prev_moves[:] + [pos.moves[child]], n)

    return aggregate_random_books(n, pos.children, pos.probs, superbooks)

def aggregate_random_books(n, positions, probs, superbooks):
    #if we have a random probability of reaching various positions
    #and prespecified optimal size N opening books
    #that start from each of those positions
    #what size N opening book should we choose overall?

    #track how many moves we're including from each position's opening book
    #initialize to all zeroes
    cnts = {p:0 for p in positions}

    #compute starting ev with no opening book
    starting_ev = sum([superbooks[p].get_starting_ev() * probs[p] for p in positions])

    output_superbook = SuperBook(None, starting_ev)
    total_ev = starting_ev

    #starting from an empty opening book
    #look through each of the positions and see how much value is gained from
    #memorizing one more move of their opening books
    #greedily choose the one that provides the best marginal ev and repeat N times
    for i in range(n):
        #list of positions with additional moves we haven't picked yet
        options = [p for p in positions if superbooks[p].get_size() > cnts[p]]
        if len(options) == 0: continue

        #we've currently memorized cnts[x] moves from position x
        #compute the marginal value of memorizing one more move from that position
        #NOTE: "marginal_ev" values assume that the opening book moves are of
        #decreasing marginal value which probably doesn't hold, but hopefully isn't too far off
        get_marginal_ev = lambda x: superbooks[x].get_marginal_ev(cnts[x]+1) * probs[x]

        #choose to learn one more move from the position with the best marginal ev
        best_pos = max(options, key = get_marginal_ev)
        marginal_ev = get_marginal_ev(best_pos)
        moves = []
        cnts[best_pos] = cnts[best_pos] + 1
        for p in positions:
            if cnts[p] == 0: continue
            for m in superbooks[p].get_book(cnts[p]).moves:
                moves.append(m)
        total_ev += marginal_ev
        assert(i+1 == len(moves))
        output_superbook.add_book(i+1, moves, total_ev)

    return output_superbook

class OpeningBook:
    #contains the optimal opening book with <= N moves
    def __init__(self, N, moves):
        super()
        #TODO: can we remove N here and store only in SuperBook?
        self.N = N
        self.moves = moves #[(prev_moves, move, total_ev)]

class SuperBook:
    #For all i in 1,..N contains the opening book of <= i moves
    #along with the expected value for using that opening book
    def __init__(self, position, starting_ev):
        super()
        self.position = position
        self.starting_ev = starting_ev
        self.books = []
        self.total_evs = []
        self.marginal_evs = []
    def add_book(self, i, moves, total_ev):
        if len(self.books) != i-1:
            print(i)
            print(self)
            raise
        self.books.append(OpeningBook(i, moves))
        self.total_evs.append(total_ev)
        if (i == 1):
            self.marginal_evs.append(total_ev - self.starting_ev)
        else:
            self.marginal_evs.append(self.total_evs[i-1] - self.total_evs[i-2])
    def get_starting_ev(self):
        return self.starting_ev
    def get_total_ev(self, k):
        return self.total_evs[k-1]
    def get_marginal_ev(self, k):
        return self.marginal_evs[k-1]
    def get_book(self, k):
        #k is the number of moves in the book
        #don't allow fetching if the evs haven't been initialized
        if self.starting_ev is None: raise
        if len(self.marginal_evs) < len(self.books): raise
        return self.books[k-1]
    def get_size(self):
        return len(self.books)
    def __str__(self):
        return str(self.position) + '\n' +\
               str(self.starting_ev) + '\n' +\
               str(self.books) + '\n' +\
               str(self.total_evs) + '\n' +\
               str(self.marginal_evs)

class GameNode:
    def __init__(self, val):
        super()
        self.val = val #fen
        #must run set_info before using the node
        self.children = None
        self.moves = None #names of edges from this node to children
        self.probs = None #probabilities from this node to children
        self.cnts = None
    def is_leaf(self):
        return len(self.children) == 0
    def set_info(self, children, moves, probs, total_cnt):
        #TODO: remove total_cnt?
        self.children = children
        self.moves = moves
        self.probs = probs
    def get_ev(self):
        #average across the evaluations of the children, weighted by their probabilities
        #only allow this for leaf nodes
        if self.is_leaf():
            return EVALUATOR.evaluate_ev(self.val, EVAL_TIME)[1]
        else:
            raise
    def __str__(self):
        return str(self.val) + '\n' + str(self.moves) + '\n' + str(self.probs)

def generate_position_stats():
    positions = {} #move_history -> {fen, move_cnts:{move: cnt}, total_cnt}

    #position info
    with open(INPUT_FILE) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in list(reader):
            default = {"fen": row["start_fen"], "move_cnts":{}, "probs":{}, "move_history":row["move_history"]}
            info = positions.setdefault(row["start_fen"],default)
            info["move_cnts"][row["move"]] = info["move_cnts"].setdefault(row["move"],0) + 1

            #set child info if not set
            child_fen = fen_plus_move(row["start_fen"], row["move"])
            full_move_list = str(eval(row["move_history"]) + [row["move"]])
            default = {"fen": child_fen, "move_cnts":{}, "probs":{}, "move_history":full_move_list}
            positions.setdefault(child_fen,default)

            #set best move info if not set
            best_move = EVALUATOR.evaluate_ev(row["start_fen"], EVAL_TIME)[0]
            best_move_fen = fen_plus_move(row["start_fen"], best_move)
            full_move_list = str(eval(row["move_history"]) + [best_move])
            default = {"fen": best_move_fen, "move_cnts":{}, "probs":{}, "move_history":full_move_list}
            positions.setdefault(best_move_fen, default)


    #warn if any positions have >0 and <20 moves --
    #this small n can ruin the data:
    #eg: make sure to play move X, which leads to a single game where the opponent
    #blunders their queen a few moves down the line
    for fen in positions:
        if sum(positions[fen]["move_cnts"].values()) > 0 and sum(positions[fen]["move_cnts"].values()) < 20:
            print('WARNING: positions with limited move counts')
            print(positions[fen]["move_history"])
            print(sum(positions[fen]["move_cnts"].values()))

    #compute move probabilities (these are the edge weights)
    for fen in positions:
        info = positions[fen]
        fen = info["fen"]

        #set counts
        total_cnt = 0
        for move in info["move_cnts"]:
            total_cnt += info["move_cnts"][move]

        #set probs
        for move in info["move_cnts"]:
            child_fen = fen_plus_move(fen, move)
            info["probs"][move] = info["move_cnts"][move] / total_cnt

        #set total cnt
        info["total_cnt"] = total_cnt

        #add best_move as an edge with weight 0
        if total_cnt > 0: #skip this step for leaf nodes
            best_move = EVALUATOR.evaluate_ev(fen, EVAL_TIME)[0]
            info["probs"].setdefault(best_move,0)
    return positions

def generate_game_tree(positions):
    #generate basic nodes for each position
    nodes = {} #move_history -> node
    for fen in positions:
        nodes[fen] = GameNode(positions[fen]["fen"])

    #create graph by fully initializing node information
    for fen in nodes:
        info = positions[fen]
        fen = info["fen"]

        children = []
        moves = {}
        probs = {}

        #set children, probs, moves
        for move in positions[fen]["probs"]:
            child_fen = fen_plus_move(fen, move)
            full_move_list = str(eval(positions[fen]["move_history"]) + [move])
            child_node = nodes[child_fen]

            children.append(child_node)
            moves[child_node] = move
            probs[child_node] = positions[fen]["probs"][move]

        nodes[fen].set_info(children, moves, probs, info["total_cnt"])

    for fen in nodes:
        pos = nodes[fen]
        sets = []
        sets.append(set(['e2e4', 'e7e5', 'f1c4', 'g8f6', 'd1f3']))
        sets.append(set(['e2e4', 'e7e5', 'f1c4', 'g8f6', 'd1f3', 'b8c6']))
        for s in sets:
            if set(positions[fen]["move_history"]) == s:
                print('evaluations')
                print()
                ev = 0
                for c in pos.children:
                    ev += pos.probs[c] * EVALUATOR.evaluate_ev(c.val, EVAL_TIME)[1]
                    print(pos.moves[c], pos.probs[c], EVALUATOR.evaluate_ev(c.val, EVAL_TIME)[1])
                print(ev)

    return nodes

def print_book(superbook, positions):
    print(superbook.get_starting_ev())
    #note: the best book might not be the one with the most moves!
    #TODO: throw out all too-large books
    #TODO: figure out how to augment the game tree such that more
    #      moves is always better
    for i in range(superbook.get_size()):
        # if x["marginal_ev"] <= 0:
        #     break
        print(i+1,superbook.get_total_ev(i+1) - superbook.get_starting_ev())
    #
    all_books = [(superbook.get_book(i),superbook.get_total_ev(i),len(superbook.get_book(i).moves),i) for i in range(1,superbook.get_size()+1)]
    best_book, best_ev, move_cnt, best_i = max(all_books, key = lambda x: x[1])
    print(best_i)
    print('move cnt:' + str(len(best_book.moves)))
    for m in sorted(best_book.moves, key=lambda x: x[0]):
        print(m)
        fen = move_history_to_fen(str(m[0]))
        print(positions[fen]["move_cnts"])
        print(positions[fen]["total_cnt"])

if __name__ == "__main__":
    #move_history -> {fen, move_cnts:{move: cnt}, total_cnt}
    positions = generate_position_stats()

    #game tree
    #nodes contain list of children
    #along with the probability,
    nodes = generate_game_tree(positions)

    starting_history = [] #['e2e4', 'e7e5'] #['e2e4', 'g8f6'] #['e2e4', 'g8f6', 'e4e5', 'f6d5']
    starting_fen = move_history_to_fen(str(starting_history))
    start_node = nodes[starting_fen]

    move_cnt = 200

    print("white")
    superbook = compute_p1_book(start_node, starting_history, move_cnt)
    print_book(superbook, positions)

    print("black")
    superbook = compute_p2_book(start_node, starting_history, move_cnt)
    print_book(superbook, positions)

    #TODO: print the node count of the last move in the tree
    EVALUATOR.save_evals()
