import json
import os
import urllib.request

P, N, B, R, Q, K = 1, 2, 3, 4, 5, 6
VALUE = (0, 100, 320, 335, 500, 950, 0)
PH = (0, 0, 1, 1, 2, 4, 0)
FILES = "abcdefgh"
KNIGHT = (33, 31, 18, 14, -14, -18, -31, -33)
KING = (1, -1, 16, -16, 15, 17, -15, -17)
DIAG = (15, 17, -15, -17)
ORTHO = (1, -1, 16, -16)
PROMOS = (Q, R, B, N)


CK = [15] * 128
for square, mask in ((0, 13), (7, 14), (4, 12),
                     (112, 7), (119, 11), (116, 3)):
    CK[square] = mask


def square(text):
    return (ord(text[1]) - 49) * 16 + ord(text[0]) - 97


def name(sq):
    return FILES[sq & 7] + str((sq >> 4) + 1)


def poskey(p):
    return hash((tuple(p.b), p.s, p.c, p.e))


class Position:
    def __init__(self, fen):
        fields = fen.split()
        self.b = [0] * 128
        self.k = [-1, -1]
        for row, text in enumerate(fields[0].split("/")):
            sq = (7 - row) * 16
            for ch in text:
                if ch.isdigit():
                    sq += int(ch)
                else:
                    pc = (" pnbrqk".index(ch.lower())) * (1 if ch.isupper() else -1)
                    self.b[sq] = pc
                    if abs(pc) == K:
                        self.k[0 if pc > 0 else 1] = sq
                    sq += 1
        self.s = 1 if fields[1] == "w" else -1
        self.c = sum(1 << "KQkq".index(c) for c in fields[2] if c in "KQkq")
        self.e = -1 if fields[3] == "-" else square(fields[3])


def attacked(p, target, by):
    b = p.b
    pawn = target - 16 * by - 1
    if any(not s & 0x88 and b[s] == by * P for s in (pawn, pawn + 2)): return True
    if any(not (target + d) & 0x88 and b[target + d] == by * N for d in KNIGHT): return True
    if any(not (target + d) & 0x88 and b[target + d] == by * K for d in KING): return True
    for dirs, pieces in ((DIAG, (B, Q)), (ORTHO, (R, Q))):
        for step in dirs:
            sq = target + step
            while not sq & 0x88:
                pc = b[sq]
                if pc:
                    if pc * by > 0 and abs(pc) in pieces:
                        return True
                    break
                sq += step
    return False


def pseudo_moves(p, captures=False):
    b, side = p.b, p.s
    for src in range(128):
        if src & 0x88:
            continue
        pc = b[src]
        if not pc or pc * side < 0:
            continue
        kind = abs(pc)
        if kind == P:
            step = side * 16
            dst = src + step
            last = 7 if side > 0 else 0
            if not captures and not dst & 0x88 and not b[dst]:
                if dst >> 4 == last:
                    for promo in PROMOS:
                        yield src, dst, promo
                else:
                    yield src, dst, 0
                    twice = dst + step
                    if src >> 4 == (1 if side > 0 else 6) and not b[twice]:
                        yield src, twice, 0
            for delta in (step - 1, step + 1):
                dst = src + delta
                if dst & 0x88:
                    continue
                if (b[dst] * side < 0 and abs(b[dst]) != K) or dst == p.e:
                    if dst >> 4 == last:
                        for promo in PROMOS:
                            yield src, dst, promo
                    else:
                        yield src, dst, 0
        elif kind in (N, K):
            for step in (KNIGHT if kind == N else KING):
                dst = src + step
                if dst & 0x88 or b[dst] * side > 0 or abs(b[dst]) == K:
                    continue
                if not captures or b[dst] * side < 0:
                    yield src, dst, 0
            if kind == K and not captures:
                home = 4 if side > 0 else 116
                if src == home and not attacked(p, src, -side):
                    ks, qs = (1, 2) if side > 0 else (4, 8)
                    if p.c & ks and b[home + 1] == b[home + 2] == 0 and b[home + 3] == side * R:
                        if not attacked(p, home + 1, -side) and not attacked(p, home + 2, -side):
                            yield home, home + 2, 0
                    if p.c & qs and b[home - 1] == b[home - 2] == b[home - 3] == 0 and b[home - 4] == side * R:
                        if not attacked(p, home - 1, -side) and not attacked(p, home - 2, -side):
                            yield home, home - 2, 0
        else:
            dirs = DIAG if kind == B else ORTHO if kind == R else DIAG + ORTHO
            for step in dirs:
                dst = src + step
                while not dst & 0x88:
                    if b[dst] * side > 0:
                        break
                    if abs(b[dst]) == K:
                        break
                    if not captures or b[dst] * side < 0:
                        yield src, dst, 0
                    if b[dst]:
                        break
                    dst += step


def make(p, move):
    src, dst, promo = move
    side, pc = p.s, p.b[src]
    captured, cap_sq = p.b[dst], dst
    old = (p.e, p.c, p.k[0], p.k[1], captured, cap_sq)
    if abs(pc) == P and dst == p.e and not captured and (src & 7) != (dst & 7):
        cap_sq = dst - side * 16
        captured = p.b[cap_sq]
        p.b[cap_sq] = 0
        old = old[:4] + (captured, cap_sq)
    p.b[src] = 0
    placed = side * promo if promo else pc
    p.b[dst] = placed
    if abs(pc) == K:
        p.k[0 if side > 0 else 1] = dst
        if abs(dst - src) == 2:
            rook_from = dst + 1 if dst > src else dst - 2
            rook_to = dst - 1 if dst > src else dst + 1
            rook = p.b[rook_from]
            p.b[rook_from] = 0
            p.b[rook_to] = rook
    p.c &= CK[src] & CK[dst]
    p.e = dst - side * 16 if abs(pc) == P and abs(dst - src) == 32 else -1
    p.s = -side
    return old, move, pc


def unmake(p, undo):
    old, (src, dst, _), pc = undo
    ep, castle, kw, kb, captured, cap_sq = old
    side = -p.s
    if abs(pc) == K and abs(dst - src) == 2:
        rook_from = dst - 1 if dst > src else dst + 1
        rook_to = dst + 1 if dst > src else dst - 2
        p.b[rook_to] = p.b[rook_from]
        p.b[rook_from] = 0
    p.b[src] = pc
    p.b[dst] = captured if cap_sq == dst else 0
    if cap_sq != dst: p.b[cap_sq] = captured
    p.s, p.e, p.c = side, ep, castle
    p.k[0], p.k[1] = kw, kb


def evaluate(p):
    material = 0
    pawns = ([s for s, c in enumerate(p.b) if c == P],
             [s for s, c in enumerate(p.b) if c == -P])
    phase = min(24, sum(PH[abs(c)] for c in p.b))
    for sq in range(128):
        if sq & 0x88:
            continue
        pc = p.b[sq]
        if not pc:
            continue
        side, kind = (1 if pc > 0 else -1), abs(pc)
        file, rank = sq & 7, sq >> 4
        if side < 0:
            rank = 7 - rank
        center = 7 - abs(2 * file - 7) - abs(2 * rank - 7)
        if kind == P:
            enemy = 0 if side < 0 else 1
            sv = 7 * rank + 2 * center
            if not any(abs((s & 7) - file) <= 1 and
                       (s >> 4 if side > 0 else 7 - (s >> 4)) > rank for s in pawns[enemy]):
                sv += (0, 0, 9, 18, 34, 58, 105, 0)[rank] * (48 - phase) // 48
        elif kind == N:
            sv = 7 * center - 18
        elif kind == B:
            sv = 4 * center - 8
        elif kind == R:
            sv = 16 if rank == 6 else 0
        elif kind == Q:
            sv = 2 * center
        else:
            mid = (28 if file in (2, 6) else 20 if file in (0, 1, 7) else -5) - 14 * rank
            sv = (mid * phase + 8 * center * (24 - phase)) // 24
        material += side * (VALUE[kind] + sv)
    return material * p.s


MATE, INF, NB = 30000, 32000, 60000


class Stopped(Exception):
    pass


class Search:

    def __init__(self, position):
        self.p = position
        self.nodes = 0
        self.tt = {}
        self.killers = [[None, None] for _ in range(96)]
        self.history = {}

    def visit(self):
        if self.nodes >= NB:
            raise Stopped
        self.nodes += 1

    def legal(self, captures=False):
        p, side, moves = self.p, self.p.s, []
        for move in pseudo_moves(p, captures):
            undo = make(p, move)
            safe = not attacked(p, p.k[0 if side > 0 else 1], -side)
            unmake(p, undo)
            if safe:
                moves.append(move)
        return moves

    def cv(self, move):
        src, dst, promo = move
        pc, victim = self.p.b[src], self.p.b[dst]
        if not victim and abs(pc) == P and dst == self.p.e and (src & 7) != (dst & 7):
            victim = -self.p.s * P
        return (10000 + 10 * VALUE[abs(victim)] - VALUE[abs(pc)] if victim else 0) + (8000 + VALUE[promo] if promo else 0)

    def order(self, moves, ttmove, ply):
        killers = self.killers[min(ply, 95)]
        return sorted(moves, key=lambda m: (m == ttmove, bool(self.cv(m)), self.cv(m),
                                             m == killers[0], m == killers[1],
                                             self.history.get((self.p.s, m[0], m[1]), 0)), reverse=True)

    def qc(self, move, ply, depth):
        ks = self.killers[min(ply, 95)]
        if move != ks[0]: ks[1], ks[0] = ks[0], move
        key = (self.p.s, move[0], move[1])
        self.history[key] = min(20000, self.history.get(key, 0) + depth * depth)

    def qsearch(self, alpha, beta, ply, qply=0):
        self.visit()
        p = self.p
        if ply >= 95: return evaluate(p)
        check = attacked(p, p.k[0 if p.s > 0 else 1], -p.s)
        stand = evaluate(p)
        if not check and stand >= beta: return beta
        if not check: alpha = max(alpha, stand)
        if qply >= 16: return stand if check else alpha
        moves = self.legal(not check)
        if check and not moves:
            return -MATE + ply
        for move in self.order(moves, None, ply):
            undo = make(p, move)
            score = -self.qsearch(-beta, -alpha, ply + 1, qply + 1)
            unmake(p, undo)
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def search(self, depth, alpha, beta, ply=0, allow_null=True):
        self.visit()
        p = self.p
        if ply >= 95:
            return evaluate(p)
        if depth <= 0:
            return self.qsearch(alpha, beta, ply)
        check = attacked(p, p.k[0 if p.s > 0 else 1], -p.s)
        if check:
            depth += 1
        oa = alpha
        key = poskey(p)
        entry = self.tt.get(key)
        ttmove = entry[3] if entry else None
        if entry and entry[0] >= depth:
            score = entry[1]
            if entry[2] == 0 or entry[2] == 1 and score >= beta or entry[2] == 2 and score <= alpha:
                return score
        static = evaluate(p)
        if (allow_null and not check and depth >= 3 and beta < MATE - 100 and static >= beta
                and any(abs(pc) in (N, B, R, Q) and pc * p.s > 0 for pc in p.b)):
            old = p.e, p.s
            p.e, p.s = -1, -p.s
            score = -self.search(depth - 3, -beta, 1 - beta, ply + 1, False)
            p.e, p.s = old
            if score >= beta:
                return score
        moves = self.legal()
        if not moves:
            return -MATE + ply if check else 0
        bm, best = None, -INF
        for index, move in enumerate(self.order(moves, ttmove, ply)):
            quiet = not self.cv(move)
            if depth == 1 and not check and quiet and static + 110 <= alpha:
                continue
            undo = make(p, move)
            reduction = 1 + (depth >= 6 and index >= 8) if depth >= 3 and index >= 4 and quiet and not check else 0
            if index == 0:
                score = -self.search(depth - 1, -beta, -alpha, ply + 1)
            else:
                score = -self.search(depth - 1 - reduction, -alpha - 1, -alpha, ply + 1)
                if score > alpha and reduction:
                    score = -self.search(depth - 1, -alpha - 1, -alpha, ply + 1)
                if alpha < score < beta:
                    score = -self.search(depth - 1, -beta, -alpha, ply + 1)
            unmake(p, undo)
            if score > best:
                best, bm = score, move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if quiet:
                    self.qc(move, ply, depth)
                break
        if best == -INF:
            best = static
        bound = 2 if best <= oa else 1 if best >= beta else 0
        self.tt[key] = (depth, best, bound, bm)
        return best

    def root(self, moves):
        best = moves[0]
        for depth in range(1, 64):
            entry = self.tt.get(poskey(self.p))
            ordered = self.order(moves, entry[3] if entry else None, 0)
            alpha, current, cs = -INF, best, -INF
            try:
                for index, move in enumerate(ordered):
                    self.visit()
                    undo = make(self.p, move)
                    if index == 0:
                        score = -self.search(depth - 1, -INF, -alpha, 1)
                    else:
                        score = -self.search(depth - 1, -alpha - 1, -alpha, 1)
                        if score > alpha:
                            score = -self.search(depth - 1, -INF, -alpha, 1)
                    unmake(self.p, undo)
                    if score > cs:
                        current, cs = move, score
                    if score > alpha:
                        alpha = score
                best = current
                self.tt[poskey(self.p)] = (depth, cs, 0, best)
                if cs >= MATE - 100:
                    break
            except Stopped:
                break
        return best


def choose(fen, legal):
    p = Position(fen)
    allowed = set(legal)
    search = Search(p)
    moves = [m for m in search.legal() if move_name(m) in allowed]
    if not moves:
        return legal[0]
    return move_name(search.root(moves))


def move_name(move):
    src, dst, promo = move
    return name(src) + name(dst) + (" pnbrq"[promo] if promo else "")


def post(path, body):
    req = urllib.request.Request(os.environ["MAKEFUN_ENV_URL"] + path,
        data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def main():
    while 1:
        game = post("/game", {})
        if game["status"] == "done":
            return
        while game["status"] == "your_move":
            game = post("/move", {"game": game["game"],
                                  "move": choose(game["fen"], game["legal_moves"])})


if __name__ == "__main__":
    main()
