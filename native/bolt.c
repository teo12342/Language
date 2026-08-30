/*
 * nboltc - a native, standalone Bolt interpreter written in C.
 *
 * This does NOT depend on Python at runtime. It is a separate,
 * from-scratch tree-walking interpreter covering a real subset of
 * the Bolt language: numbers, strings, booleans, nil, lists, maps,
 * functions/closures, control flow, and a Win32-native game-dev
 * builtin set (window/draw/input/sound) that replaces the old
 * tkinter/winsound-backed builtins with real Win32 GDI + Beep().
 *
 * Scope, honestly: this is a new, smaller implementation, not a
 * line-for-line port of the Python VM. Things not yet in here:
 * gradual typing, tensors, modules/import(), pyimport() (which by
 * definition needs Python and is dropped, not reimplemented),
 * draw_image/play_sound (need an image/audio decoder this file
 * doesn't have yet), and a real garbage collector (values are
 * arena-leaked for the process lifetime, which is fine for
 * short-lived scripts and games, not for long-running servers).
 *
 * Build (MSVC):   cl /O2 /nologo bolt.c /Fe:nboltc.exe user32.lib gdi32.lib winmm.lib
 * Build (gcc):    gcc -O2 -o nboltc.exe bolt.c -lgdi32 -luser32 -lwinmm
 * Run:            nboltc.exe script.bo
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <stdbool.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

/* ============================= Values ============================= */

typedef struct Value Value;
typedef struct Env Env;
typedef struct Stmt Stmt;
typedef struct Expr Expr;

typedef enum {
    V_NIL, V_BOOL, V_NUM, V_STR, V_LIST, V_MAP, V_FUNC, V_NATIVE, V_WINDOW
} VType;

typedef struct { char *key; Value *val; } MapEntry;

typedef struct {
    char **params; int nparams;
    Stmt **body; int nbody;
    Env *closure;
    char *name;
} FuncVal;

typedef Value *(*NativeFn)(Value **args, int nargs);

#ifdef _WIN32
typedef struct {
    HWND hwnd;
    HDC memDC;
    HBITMAP bmp;
    int w, h;
    bool open;
    bool keys[256];
    int mouseX, mouseY;
    bool mouseLeft, mouseRight;
    LARGE_INTEGER qpcFreq, lastTick;
} WindowVal;
#else
typedef struct { int w, h; } WindowVal;
#endif

struct Value {
    VType type;
    union {
        bool b;
        double n;
        char *s;
        struct { Value **items; int len, cap; } list;
        struct { MapEntry *entries; int len, cap; } map;
        FuncVal *fn;
        NativeFn native;
        WindowVal *win;
    } as;
};

static Value V_NIL_SINGLETON = { V_NIL, {0} };
static Value V_TRUE_SINGLETON = { V_BOOL, { .b = true } };
static Value V_FALSE_SINGLETON = { V_BOOL, { .b = false } };

static Value *mk_nil(void) { return &V_NIL_SINGLETON; }
static Value *mk_bool(bool b) { return b ? &V_TRUE_SINGLETON : &V_FALSE_SINGLETON; }
static Value *mk_num(double n) { Value *v = malloc(sizeof(Value)); v->type = V_NUM; v->as.n = n; return v; }
static Value *mk_str(const char *s) { Value *v = malloc(sizeof(Value)); v->type = V_STR; v->as.s = strdup(s); return v; }
static Value *mk_list(void) { Value *v = malloc(sizeof(Value)); v->type = V_LIST; v->as.list.items = NULL; v->as.list.len = 0; v->as.list.cap = 0; return v; }
static Value *mk_map(void) { Value *v = malloc(sizeof(Value)); v->type = V_MAP; v->as.map.entries = NULL; v->as.map.len = 0; v->as.map.cap = 0; return v; }

static void list_push(Value *list, Value *item) {
    if (list->as.list.len >= list->as.list.cap) {
        list->as.list.cap = list->as.list.cap ? list->as.list.cap * 2 : 4;
        list->as.list.items = realloc(list->as.list.items, sizeof(Value*) * list->as.list.cap);
    }
    list->as.list.items[list->as.list.len++] = item;
}

static void map_set(Value *map, const char *key, Value *val) {
    for (int i = 0; i < map->as.map.len; i++) {
        if (strcmp(map->as.map.entries[i].key, key) == 0) { map->as.map.entries[i].val = val; return; }
    }
    if (map->as.map.len >= map->as.map.cap) {
        map->as.map.cap = map->as.map.cap ? map->as.map.cap * 2 : 4;
        map->as.map.entries = realloc(map->as.map.entries, sizeof(MapEntry) * map->as.map.cap);
    }
    map->as.map.entries[map->as.map.len].key = strdup(key);
    map->as.map.entries[map->as.map.len].val = val;
    map->as.map.len++;
}

static Value *map_get(Value *map, const char *key) {
    for (int i = 0; i < map->as.map.len; i++)
        if (strcmp(map->as.map.entries[i].key, key) == 0) return map->as.map.entries[i].val;
    return mk_nil();
}

static bool truthy(Value *v) {
    switch (v->type) {
        case V_NIL: return false;
        case V_BOOL: return v->as.b;
        case V_NUM: return v->as.n != 0;
        case V_STR: return v->as.s[0] != '\0';
        case V_LIST: return v->as.list.len != 0;
        default: return true;
    }
}

static char *num_to_str(double n) {
    char buf[64];
    if (n == (long long)n && fabs(n) < 1e15) snprintf(buf, sizeof(buf), "%lld", (long long)n);
    else snprintf(buf, sizeof(buf), "%g", n);
    return strdup(buf);
}

static void value_print(Value *v, FILE *out) {
    switch (v->type) {
        case V_NIL: fprintf(out, "nil"); break;
        case V_BOOL: fprintf(out, v->as.b ? "true" : "false"); break;
        case V_NUM: { char *s = num_to_str(v->as.n); fprintf(out, "%s", s); free(s); break; }
        case V_STR: fprintf(out, "%s", v->as.s); break;
        case V_LIST: {
            fprintf(out, "[");
            for (int i = 0; i < v->as.list.len; i++) {
                if (i) fprintf(out, ", ");
                if (v->as.list.items[i]->type == V_STR) fprintf(out, "\"%s\"", v->as.list.items[i]->as.s);
                else value_print(v->as.list.items[i], out);
            }
            fprintf(out, "]");
            break;
        }
        case V_MAP: {
            fprintf(out, "{");
            for (int i = 0; i < v->as.map.len; i++) {
                if (i) fprintf(out, ", ");
                fprintf(out, "\"%s\": ", v->as.map.entries[i].key);
                Value *mv = v->as.map.entries[i].val;
                if (mv->type == V_STR) fprintf(out, "\"%s\"", mv->as.s); else value_print(mv, out);
            }
            fprintf(out, "}");
            break;
        }
        case V_FUNC: fprintf(out, "<func %s>", v->as.fn->name ? v->as.fn->name : "anon"); break;
        default: fprintf(out, "<value>"); break;
    }
}

/* ============================== Lexer ============================== */

typedef enum {
    T_NUM, T_STR, T_IDENT, T_KW,
    T_PLUS, T_MINUS, T_STAR, T_SLASH, T_PERCENT, T_POW,
    T_EQ, T_EQEQ, T_NEQ, T_LT, T_LE, T_GT, T_GE,
    T_LPAREN, T_RPAREN, T_LBRACE, T_RBRACE, T_LBRACK, T_RBRACK,
    T_COMMA, T_COLON, T_DOT, T_SEMI, T_EOF
} TokType;

typedef struct { TokType type; char *text; double num; int line; } Token;

static const char *KEYWORDS[] = {
    "let","func","if","else","while","for","in","return","break","continue",
    "true","false","nil","and","or","not", NULL
};

typedef struct { const char *src; int pos, len, line; Token *toks; int ntoks, cap; } Lexer;

static bool is_kw(const char *s) { for (int i = 0; KEYWORDS[i]; i++) if (strcmp(KEYWORDS[i], s) == 0) return true; return false; }

static void push_tok(Lexer *lx, TokType t, const char *text, double num) {
    if (lx->ntoks >= lx->cap) { lx->cap = lx->cap ? lx->cap * 2 : 256; lx->toks = realloc(lx->toks, sizeof(Token) * lx->cap); }
    lx->toks[lx->ntoks].type = t;
    lx->toks[lx->ntoks].text = text ? strdup(text) : NULL;
    lx->toks[lx->ntoks].num = num;
    lx->toks[lx->ntoks].line = lx->line;
    lx->ntoks++;
}

static void lex(Lexer *lx) {
    while (lx->pos < lx->len) {
        char c = lx->src[lx->pos];
        if (c == '\n') { lx->line++; lx->pos++; continue; }
        if (isspace((unsigned char)c)) { lx->pos++; continue; }
        if (c == '#') { while (lx->pos < lx->len && lx->src[lx->pos] != '\n') lx->pos++; continue; }
        if (isdigit((unsigned char)c)) {
            int start = lx->pos;
            while (lx->pos < lx->len && (isdigit((unsigned char)lx->src[lx->pos]) || lx->src[lx->pos] == '.')) lx->pos++;
            char buf[64]; int n = lx->pos - start; if (n > 63) n = 63;
            memcpy(buf, lx->src + start, n); buf[n] = 0;
            push_tok(lx, T_NUM, NULL, atof(buf));
            continue;
        }
        if (c == '"') {
            lx->pos++; char buf[4096]; int bi = 0;
            while (lx->pos < lx->len && lx->src[lx->pos] != '"') {
                char ch = lx->src[lx->pos++];
                if (ch == '\\' && lx->pos < lx->len) {
                    char esc = lx->src[lx->pos++];
                    if (esc == 'n') ch = '\n'; else if (esc == 't') ch = '\t'; else ch = esc;
                }
                if (bi < 4095) buf[bi++] = ch;
            }
            lx->pos++; buf[bi] = 0;
            push_tok(lx, T_STR, buf, 0);
            continue;
        }
        if (isalpha((unsigned char)c) || c == '_') {
            int start = lx->pos;
            while (lx->pos < lx->len && (isalnum((unsigned char)lx->src[lx->pos]) || lx->src[lx->pos] == '_')) lx->pos++;
            char buf[256]; int n = lx->pos - start; if (n > 255) n = 255;
            memcpy(buf, lx->src + start, n); buf[n] = 0;
            push_tok(lx, is_kw(buf) ? T_KW : T_IDENT, buf, 0);
            continue;
        }
        /* two-char operators */
        if (c == '*' && lx->src[lx->pos+1] == '*') { push_tok(lx, T_POW, "**", 0); lx->pos += 2; continue; }
        if (c == '=' && lx->src[lx->pos+1] == '=') { push_tok(lx, T_EQEQ, "==", 0); lx->pos += 2; continue; }
        if (c == '!' && lx->src[lx->pos+1] == '=') { push_tok(lx, T_NEQ, "!=", 0); lx->pos += 2; continue; }
        if (c == '<' && lx->src[lx->pos+1] == '=') { push_tok(lx, T_LE, "<=", 0); lx->pos += 2; continue; }
        if (c == '>' && lx->src[lx->pos+1] == '=') { push_tok(lx, T_GE, ">=", 0); lx->pos += 2; continue; }
        switch (c) {
            case '+': push_tok(lx, T_PLUS, "+", 0); break;
            case '-': push_tok(lx, T_MINUS, "-", 0); break;
            case '*': push_tok(lx, T_STAR, "*", 0); break;
            case '/': push_tok(lx, T_SLASH, "/", 0); break;
            case '%': push_tok(lx, T_PERCENT, "%", 0); break;
            case '=': push_tok(lx, T_EQ, "=", 0); break;
            case '<': push_tok(lx, T_LT, "<", 0); break;
            case '>': push_tok(lx, T_GT, ">", 0); break;
            case '(': push_tok(lx, T_LPAREN, "(", 0); break;
            case ')': push_tok(lx, T_RPAREN, ")", 0); break;
            case '{': push_tok(lx, T_LBRACE, "{", 0); break;
            case '}': push_tok(lx, T_RBRACE, "}", 0); break;
            case '[': push_tok(lx, T_LBRACK, "[", 0); break;
            case ']': push_tok(lx, T_RBRACK, "]", 0); break;
            case ',': push_tok(lx, T_COMMA, ",", 0); break;
            case ':': push_tok(lx, T_COLON, ":", 0); break;
            case '.': push_tok(lx, T_DOT, ".", 0); break;
            case ';': push_tok(lx, T_SEMI, ";", 0); break;
            default: fprintf(stderr, "bolt: unexpected char '%c' at line %d\n", c, lx->line); exit(1);
        }
        lx->pos++;
    }
    push_tok(lx, T_EOF, NULL, 0);
}

/* ================================ AST ================================ */

typedef enum {
    E_NUM, E_STR, E_BOOL, E_NIL, E_IDENT, E_LIST, E_MAP,
    E_BINOP, E_UNARY, E_CALL, E_INDEX, E_ASSIGN, E_INDEX_ASSIGN,
    E_FUNC, E_AND, E_OR
} ExprType;

struct Expr {
    ExprType type;
    double num; char *str; bool boolean;
    char *op;
    Expr *a, *b, *c;
    Expr **items; int nitems;
    char **keys;
    Expr **args; int nargs;
    char **params; int nparams;
    Stmt **body; int nbody;
    char *fname;
};

typedef enum {
    S_LET, S_EXPR, S_IF, S_WHILE, S_FORIN, S_RETURN, S_BREAK, S_CONTINUE, S_FUNC, S_BLOCK
} StmtType;

struct Stmt {
    StmtType type;
    char *name;
    Expr *expr, *cond, *iter;
    Stmt **body; int nbody;
    Stmt **elseBody; int nelse;
    char **params; int nparams;
};

/* ============================== Parser ============================== */

typedef struct { Token *toks; int pos; } Parser;

static Token *cur(Parser *p) { return &p->toks[p->pos]; }
static Token *advance(Parser *p) { return &p->toks[p->pos++]; }
static bool check_kw(Parser *p, const char *kw) { return cur(p)->type == T_KW && strcmp(cur(p)->text, kw) == 0; }
static bool match_kw(Parser *p, const char *kw) { if (check_kw(p, kw)) { p->pos++; return true; } return false; }
static bool match(Parser *p, TokType t) { if (cur(p)->type == t) { p->pos++; return true; } return false; }
static void expect(Parser *p, TokType t, const char *what) {
    if (!match(p, t)) { fprintf(stderr, "bolt: parse error near line %d, expected %s\n", cur(p)->line, what); exit(1); }
}

static Expr *parse_expr(Parser *p);
static Stmt *parse_stmt(Parser *p);
static Stmt **parse_block(Parser *p, int *count);

static Expr *new_expr(ExprType t) { Expr *e = calloc(1, sizeof(Expr)); e->type = t; return e; }

static Expr *parse_call_index(Parser *p, Expr *base) {
    for (;;) {
        if (match(p, T_LPAREN)) {
            Expr *e = new_expr(E_CALL); e->a = base;
            Expr **args = NULL; int n = 0;
            if (cur(p)->type != T_RPAREN) {
                for (;;) {
                    args = realloc(args, sizeof(Expr*) * (n+1));
                    args[n++] = parse_expr(p);
                    if (!match(p, T_COMMA)) break;
                }
            }
            expect(p, T_RPAREN, ")");
            e->args = args; e->nargs = n;
            base = e;
        } else if (match(p, T_LBRACK)) {
            Expr *idx = parse_expr(p);
            expect(p, T_RBRACK, "]");
            Expr *e = new_expr(E_INDEX); e->a = base; e->b = idx;
            base = e;
        } else if (match(p, T_DOT)) {
            char *name = advance(p)->text;
            Expr *e = new_expr(E_INDEX); e->a = base;
            Expr *k = new_expr(E_STR); k->str = strdup(name);
            e->b = k;
            base = e;
        } else break;
    }
    return base;
}

static Expr *parse_primary(Parser *p) {
    Token *t = cur(p);
    if (t->type == T_NUM) { p->pos++; Expr *e = new_expr(E_NUM); e->num = t->num; return parse_call_index(p, e); }
    if (t->type == T_STR) { p->pos++; Expr *e = new_expr(E_STR); e->str = strdup(t->text); return parse_call_index(p, e); }
    if (check_kw(p, "true")) { p->pos++; Expr *e = new_expr(E_BOOL); e->boolean = true; return e; }
    if (check_kw(p, "false")) { p->pos++; Expr *e = new_expr(E_BOOL); e->boolean = false; return e; }
    if (check_kw(p, "nil")) { p->pos++; return new_expr(E_NIL); }
    if (check_kw(p, "not")) { p->pos++; Expr *e = new_expr(E_UNARY); e->op = strdup("not"); e->a = parse_primary(p); return e; }
    if (check_kw(p, "func")) {
        p->pos++;
        expect(p, T_LPAREN, "(");
        char **params = NULL; int np = 0;
        if (cur(p)->type != T_RPAREN) {
            for (;;) {
                params = realloc(params, sizeof(char*) * (np+1));
                params[np++] = strdup(advance(p)->text);
                if (cur(p)->type == T_COLON) { p->pos++; advance(p); }
                if (!match(p, T_COMMA)) break;
            }
        }
        expect(p, T_RPAREN, ")");
        if (cur(p)->type == T_COLON) { p->pos++; advance(p); }
        expect(p, T_LBRACE, "{");
        int nb; Stmt **body = parse_block(p, &nb);
        Expr *e = new_expr(E_FUNC); e->params = params; e->nparams = np; e->body = body; e->nbody = nb;
        return e;
    }
    if (t->type == T_IDENT) {
        p->pos++;
        Expr *e = new_expr(E_IDENT); e->str = strdup(t->text);
        return parse_call_index(p, e);
    }
    if (match(p, T_LPAREN)) { Expr *e = parse_expr(p); expect(p, T_RPAREN, ")"); return parse_call_index(p, e); }
    if (match(p, T_LBRACK)) {
        Expr *e = new_expr(E_LIST);
        Expr **items = NULL; int n = 0;
        if (cur(p)->type != T_RBRACK) {
            for (;;) {
                if (cur(p)->type == T_LBRACK) { /* nested list literal handled by recursion */ }
                items = realloc(items, sizeof(Expr*) * (n+1));
                items[n++] = parse_expr(p);
                if (!match(p, T_COMMA)) break;
            }
        }
        expect(p, T_RBRACK, "]");
        e->items = items; e->nitems = n;
        return parse_call_index(p, e);
    }
    if (match(p, T_LBRACE)) {
        Expr *e = new_expr(E_MAP);
        Expr **vals = NULL; char **keys = NULL; int n = 0;
        if (cur(p)->type != T_RBRACE) {
            for (;;) {
                char *key = strdup(advance(p)->text);
                expect(p, T_COLON, ":");
                Expr *v = parse_expr(p);
                keys = realloc(keys, sizeof(char*) * (n+1)); keys[n] = key;
                vals = realloc(vals, sizeof(Expr*) * (n+1)); vals[n] = v;
                n++;
                if (!match(p, T_COMMA)) break;
            }
        }
        expect(p, T_RBRACE, "}");
        e->keys = keys; e->items = vals; e->nitems = n;
        return e;
    }
    fprintf(stderr, "bolt: parse error near line %d (unexpected token)\n", t->line);
    exit(1);
}

static Expr *parse_unary(Parser *p) {
    if (cur(p)->type == T_MINUS) { p->pos++; Expr *e = new_expr(E_UNARY); e->op = strdup("-"); e->a = parse_unary(p); return e; }
    return parse_primary(p);
}
static Expr *parse_pow(Parser *p) {
    Expr *l = parse_unary(p);
    if (match(p, T_POW)) { Expr *e = new_expr(E_BINOP); e->op = strdup("**"); e->a = l; e->b = parse_pow(p); return e; }
    return l;
}
static Expr *parse_mul(Parser *p) {
    Expr *l = parse_pow(p);
    while (cur(p)->type == T_STAR || cur(p)->type == T_SLASH || cur(p)->type == T_PERCENT) {
        char *op = advance(p)->text;
        Expr *e = new_expr(E_BINOP); e->op = strdup(op); e->a = l; e->b = parse_pow(p); l = e;
    }
    return l;
}
static Expr *parse_add(Parser *p) {
    Expr *l = parse_mul(p);
    while (cur(p)->type == T_PLUS || cur(p)->type == T_MINUS) {
        char *op = advance(p)->text;
        Expr *e = new_expr(E_BINOP); e->op = strdup(op); e->a = l; e->b = parse_mul(p); l = e;
    }
    return l;
}
static Expr *parse_cmp(Parser *p) {
    Expr *l = parse_add(p);
    while (cur(p)->type == T_LT || cur(p)->type == T_LE || cur(p)->type == T_GT || cur(p)->type == T_GE ||
           cur(p)->type == T_EQEQ || cur(p)->type == T_NEQ) {
        char *op = advance(p)->text;
        Expr *e = new_expr(E_BINOP); e->op = strdup(op); e->a = l; e->b = parse_add(p); l = e;
    }
    return l;
}
static Expr *parse_and(Parser *p) {
    Expr *l = parse_cmp(p);
    while (check_kw(p, "and")) { p->pos++; Expr *e = new_expr(E_AND); e->a = l; e->b = parse_cmp(p); l = e; }
    return l;
}
static Expr *parse_or(Parser *p) {
    Expr *l = parse_and(p);
    while (check_kw(p, "or")) { p->pos++; Expr *e = new_expr(E_OR); e->a = l; e->b = parse_and(p); l = e; }
    return l;
}
static Expr *parse_expr(Parser *p) {
    Expr *l = parse_or(p);
    if (cur(p)->type == T_EQ) {
        p->pos++;
        Expr *rhs = parse_expr(p);
        if (l->type == E_IDENT) { Expr *e = new_expr(E_ASSIGN); e->str = l->str; e->b = rhs; return e; }
        if (l->type == E_INDEX) { Expr *e = new_expr(E_INDEX_ASSIGN); e->a = l->a; e->b = l->b; e->c = rhs; return e; }
        fprintf(stderr, "bolt: invalid assignment target\n"); exit(1);
    }
    return l;
}

static Stmt *new_stmt(StmtType t) { Stmt *s = calloc(1, sizeof(Stmt)); s->type = t; return s; }

static Stmt *parse_stmt(Parser *p) {
    if (match_kw(p, "let")) {
        char *name = strdup(advance(p)->text);
        if (cur(p)->type == T_COLON) { p->pos++; advance(p); }
        expect(p, T_EQ, "=");
        Expr *val = parse_expr(p);
        Stmt *s = new_stmt(S_LET); s->name = name; s->expr = val;
        return s;
    }
    if (match_kw(p, "func")) {
        char *name = strdup(advance(p)->text);
        expect(p, T_LPAREN, "(");
        char **params = NULL; int np = 0;
        if (cur(p)->type != T_RPAREN) {
            for (;;) {
                params = realloc(params, sizeof(char*) * (np+1));
                params[np++] = strdup(advance(p)->text);
                if (cur(p)->type == T_COLON) { p->pos++; advance(p); }
                if (!match(p, T_COMMA)) break;
            }
        }
        expect(p, T_RPAREN, ")");
        if (cur(p)->type == T_COLON) { p->pos++; advance(p); }
        expect(p, T_LBRACE, "{");
        int nb; Stmt **body = parse_block(p, &nb);
        Stmt *s = new_stmt(S_FUNC); s->name = name; s->params = params; s->nparams = np; s->body = body; s->nbody = nb;
        return s;
    }
    if (match_kw(p, "if")) {
        Expr *cond = parse_expr(p);
        expect(p, T_LBRACE, "{");
        int nb; Stmt **body = parse_block(p, &nb);
        Stmt *s = new_stmt(S_IF); s->cond = cond; s->body = body; s->nbody = nb;
        if (match_kw(p, "else")) {
            if (check_kw(p, "if")) {
                Stmt *elif = parse_stmt(p);
                s->elseBody = malloc(sizeof(Stmt*)); s->elseBody[0] = elif; s->nelse = 1;
            } else {
                expect(p, T_LBRACE, "{");
                int ne; s->elseBody = parse_block(p, &ne); s->nelse = ne;
            }
        }
        return s;
    }
    if (match_kw(p, "while")) {
        Expr *cond = parse_expr(p);
        expect(p, T_LBRACE, "{");
        int nb; Stmt **body = parse_block(p, &nb);
        Stmt *s = new_stmt(S_WHILE); s->cond = cond; s->body = body; s->nbody = nb;
        return s;
    }
    if (match_kw(p, "for")) {
        char *name = strdup(advance(p)->text);
        if (!match_kw(p, "in")) { fprintf(stderr, "bolt: expected 'in' in for-loop\n"); exit(1); }
        Expr *iter = parse_expr(p);
        expect(p, T_LBRACE, "{");
        int nb; Stmt **body = parse_block(p, &nb);
        Stmt *s = new_stmt(S_FORIN); s->name = name; s->iter = iter; s->body = body; s->nbody = nb;
        return s;
    }
    if (match_kw(p, "return")) {
        Stmt *s = new_stmt(S_RETURN);
        if (cur(p)->type != T_RBRACE && cur(p)->type != T_EOF) s->expr = parse_expr(p);
        return s;
    }
    if (match_kw(p, "break")) return new_stmt(S_BREAK);
    if (match_kw(p, "continue")) return new_stmt(S_CONTINUE);
    Expr *e = parse_expr(p);
    Stmt *s = new_stmt(S_EXPR); s->expr = e;
    return s;
}

static Stmt **parse_block(Parser *p, int *count) {
    Stmt **body = NULL; int n = 0;
    while (cur(p)->type != T_RBRACE && cur(p)->type != T_EOF) {
        body = realloc(body, sizeof(Stmt*) * (n+1));
        body[n++] = parse_stmt(p);
        while (match(p, T_SEMI)) {}
    }
    expect(p, T_RBRACE, "}");
    *count = n;
    return body;
}

static Stmt **parse_program(Parser *p, int *count) {
    Stmt **body = NULL; int n = 0;
    while (cur(p)->type != T_EOF) {
        body = realloc(body, sizeof(Stmt*) * (n+1));
        body[n++] = parse_stmt(p);
        while (match(p, T_SEMI)) {}
    }
    *count = n;
    return body;
}

/* ============================ Environment ============================ */

typedef struct { char *name; Value *val; } Binding;
struct Env { Binding *vars; int len, cap; Env *parent; };

static Env *env_new(Env *parent) { Env *e = malloc(sizeof(Env)); e->vars = NULL; e->len = 0; e->cap = 0; e->parent = parent; return e; }

static void env_define(Env *e, const char *name, Value *v) {
    for (int i = 0; i < e->len; i++) if (strcmp(e->vars[i].name, name) == 0) { e->vars[i].val = v; return; }
    if (e->len >= e->cap) { e->cap = e->cap ? e->cap * 2 : 8; e->vars = realloc(e->vars, sizeof(Binding) * e->cap); }
    e->vars[e->len].name = strdup(name); e->vars[e->len].val = v; e->len++;
}

static bool env_set(Env *e, const char *name, Value *v) {
    for (Env *cur = e; cur; cur = cur->parent)
        for (int i = 0; i < cur->len; i++)
            if (strcmp(cur->vars[i].name, name) == 0) { cur->vars[i].val = v; return true; }
    return false;
}

static Value *env_get(Env *e, const char *name) {
    for (Env *cur = e; cur; cur = cur->parent)
        for (int i = 0; i < cur->len; i++)
            if (strcmp(cur->vars[i].name, name) == 0) return cur->vars[i].val;
    fprintf(stderr, "bolt: undefined name '%s'\n", name);
    exit(1);
}

/* ============================= Interpreter ============================= */

typedef enum { SIG_NONE, SIG_RETURN, SIG_BREAK, SIG_CONTINUE } Signal;
static Signal g_signal = SIG_NONE;
static Value *g_retval = NULL;

static Value *eval(Expr *e, Env *env);
static void exec_block(Stmt **body, int n, Env *env);

static Value *call_func(Value *fn, Value **args, int nargs) {
    if (fn->type == V_NATIVE) return fn->as.native(args, nargs);
    if (fn->type != V_FUNC) { fprintf(stderr, "bolt: value is not callable\n"); exit(1); }
    FuncVal *f = fn->as.fn;
    Env *call_env = env_new(f->closure);
    for (int i = 0; i < f->nparams; i++)
        env_define(call_env, f->params[i], i < nargs ? args[i] : mk_nil());
    exec_block(f->body, f->nbody, call_env);
    Value *ret = mk_nil();
    if (g_signal == SIG_RETURN) { ret = g_retval ? g_retval : mk_nil(); }
    g_signal = SIG_NONE; g_retval = NULL;
    return ret;
}

static Value *native_call(Env *env, const char *name, Expr **argExprs, int nargs);

static Value *eval(Expr *e, Env *env) {
    switch (e->type) {
        case E_NUM: return mk_num(e->num);
        case E_STR: return mk_str(e->str);
        case E_BOOL: return mk_bool(e->boolean);
        case E_NIL: return mk_nil();
        case E_IDENT: return env_get(env, e->str);
        case E_LIST: {
            Value *l = mk_list();
            for (int i = 0; i < e->nitems; i++) list_push(l, eval(e->items[i], env));
            return l;
        }
        case E_MAP: {
            Value *m = mk_map();
            for (int i = 0; i < e->nitems; i++) map_set(m, e->keys[i], eval(e->items[i], env));
            return m;
        }
        case E_AND: { Value *l = eval(e->a, env); if (!truthy(l)) return l; return eval(e->b, env); }
        case E_OR: { Value *l = eval(e->a, env); if (truthy(l)) return l; return eval(e->b, env); }
        case E_UNARY: {
            Value *v = eval(e->a, env);
            if (strcmp(e->op, "-") == 0) return mk_num(-v->as.n);
            if (strcmp(e->op, "not") == 0) return mk_bool(!truthy(v));
            return mk_nil();
        }
        case E_BINOP: {
            Value *l = eval(e->a, env), *r = eval(e->b, env);
            const char *op = e->op;
            if (strcmp(op, "+") == 0) {
                if (l->type == V_STR || r->type == V_STR) {
                    char lb[256], rb[256];
                    const char *ls = l->type == V_STR ? l->as.s : (l->type == V_NUM ? (snprintf(lb,256,"%s",num_to_str(l->as.n)),lb) : "");
                    const char *rs = r->type == V_STR ? r->as.s : (r->type == V_NUM ? (snprintf(rb,256,"%s",num_to_str(r->as.n)),rb) : "");
                    char *buf = malloc(strlen(ls) + strlen(rs) + 1);
                    strcpy(buf, ls); strcat(buf, rs);
                    Value *v = mk_str(buf); free(buf); return v;
                }
                return mk_num(l->as.n + r->as.n);
            }
            if (strcmp(op, "-") == 0) return mk_num(l->as.n - r->as.n);
            if (strcmp(op, "*") == 0) {
                if (l->type == V_STR && r->type == V_NUM) {
                    int n = (int)r->as.n; size_t sl = strlen(l->as.s);
                    char *buf = malloc(sl * (n>0?n:0) + 1); buf[0] = 0;
                    for (int i = 0; i < n; i++) strcat(buf, l->as.s);
                    Value *v = mk_str(buf); free(buf); return v;
                }
                return mk_num(l->as.n * r->as.n);
            }
            if (strcmp(op, "/") == 0) return mk_num(l->as.n / r->as.n);
            if (strcmp(op, "%") == 0) return mk_num(fmod(l->as.n, r->as.n));
            if (strcmp(op, "**") == 0) return mk_num(pow(l->as.n, r->as.n));
            if (strcmp(op, "==") == 0) {
                if (l->type != r->type) return mk_bool(false);
                if (l->type == V_NUM) return mk_bool(l->as.n == r->as.n);
                if (l->type == V_STR) return mk_bool(strcmp(l->as.s, r->as.s) == 0);
                if (l->type == V_BOOL) return mk_bool(l->as.b == r->as.b);
                if (l->type == V_NIL) return mk_bool(true);
                return mk_bool(l == r);
            }
            if (strcmp(op, "!=") == 0) { Value *eqv = eval(e, env); (void)eqv; }
            if (strcmp(op, "<") == 0) return mk_bool(l->as.n < r->as.n);
            if (strcmp(op, "<=") == 0) return mk_bool(l->as.n <= r->as.n);
            if (strcmp(op, ">") == 0) return mk_bool(l->as.n > r->as.n);
            if (strcmp(op, ">=") == 0) return mk_bool(l->as.n >= r->as.n);
            return mk_nil();
        }
        case E_INDEX: {
            Value *base = eval(e->a, env);
            Value *key = eval(e->b, env);
            if (base->type == V_LIST) {
                int i = (int)key->as.n;
                if (i < 0 || i >= base->as.list.len) { fprintf(stderr, "bolt: list index out of range\n"); exit(1); }
                return base->as.list.items[i];
            }
            if (base->type == V_MAP) return map_get(base, key->as.s);
            if (base->type == V_STR) {
                int i = (int)key->as.n;
                char buf[2] = { base->as.s[i], 0 };
                return mk_str(buf);
            }
            return mk_nil();
        }
        case E_INDEX_ASSIGN: {
            Value *base = eval(e->a, env);
            Value *key = eval(e->b, env);
            Value *val = eval(e->c, env);
            if (base->type == V_LIST) { int i = (int)key->as.n; base->as.list.items[i] = val; }
            else if (base->type == V_MAP) map_set(base, key->as.s, val);
            return val;
        }
        case E_ASSIGN: {
            Value *val = eval(e->b, env);
            if (!env_set(env, e->str, val)) env_define(env, e->str, val);
            return val;
        }
        case E_FUNC: {
            Value *v = malloc(sizeof(Value)); v->type = V_FUNC;
            FuncVal *f = malloc(sizeof(FuncVal));
            f->params = e->params; f->nparams = e->nparams;
            f->body = e->body; f->nbody = e->nbody;
            f->closure = env; f->name = NULL;
            v->as.fn = f;
            return v;
        }
        case E_CALL: {
            if (e->a->type == E_IDENT) {
                Value *r = native_call(env, e->a->str, e->args, e->nargs);
                if (r) return r;
            }
            Value *fn = eval(e->a, env);
            Value **args = malloc(sizeof(Value*) * (e->nargs ? e->nargs : 1));
            for (int i = 0; i < e->nargs; i++) args[i] = eval(e->args[i], env);
            Value *r = call_func(fn, args, e->nargs);
            free(args);
            return r;
        }
    }
    return mk_nil();
}

static void exec_stmt(Stmt *s, Env *env) {
    if (g_signal != SIG_NONE) return;
    switch (s->type) {
        case S_LET: env_define(env, s->name, eval(s->expr, env)); break;
        case S_EXPR: eval(s->expr, env); break;
        case S_FUNC: {
            Value *v = malloc(sizeof(Value)); v->type = V_FUNC;
            FuncVal *f = malloc(sizeof(FuncVal));
            f->params = s->params; f->nparams = s->nparams;
            f->body = s->body; f->nbody = s->nbody;
            f->closure = env; f->name = s->name;
            v->as.fn = f;
            env_define(env, s->name, v);
            break;
        }
        case S_IF: {
            if (truthy(eval(s->cond, env))) { Env *b = env_new(env); exec_block(s->body, s->nbody, b); }
            else if (s->nelse) { Env *b = env_new(env); exec_block(s->elseBody, s->nelse, b); }
            break;
        }
        case S_WHILE: {
            while (truthy(eval(s->cond, env))) {
                Env *b = env_new(env);
                exec_block(s->body, s->nbody, b);
                if (g_signal == SIG_BREAK) { g_signal = SIG_NONE; break; }
                if (g_signal == SIG_CONTINUE) { g_signal = SIG_NONE; continue; }
                if (g_signal == SIG_RETURN) break;
            }
            break;
        }
        case S_FORIN: {
            Value *iter = eval(s->iter, env);
            if (iter->type == V_LIST) {
                for (int i = 0; i < iter->as.list.len; i++) {
                    Env *b = env_new(env);
                    env_define(b, s->name, iter->as.list.items[i]);
                    exec_block(s->body, s->nbody, b);
                    if (g_signal == SIG_BREAK) { g_signal = SIG_NONE; break; }
                    if (g_signal == SIG_CONTINUE) { g_signal = SIG_NONE; continue; }
                    if (g_signal == SIG_RETURN) break;
                }
            }
            break;
        }
        case S_RETURN: g_retval = s->expr ? eval(s->expr, env) : mk_nil(); g_signal = SIG_RETURN; break;
        case S_BREAK: g_signal = SIG_BREAK; break;
        case S_CONTINUE: g_signal = SIG_CONTINUE; break;
        case S_BLOCK: exec_block(s->body, s->nbody, env_new(env)); break;
    }
}

static void exec_block(Stmt **body, int n, Env *env) {
    for (int i = 0; i < n && g_signal == SIG_NONE; i++) exec_stmt(body[i], env);
}

/* ============================ Win32 game builtins ============================ */

#ifdef _WIN32
static WindowVal *g_activeWindows[16];
static int g_nActiveWindows = 0;

static LRESULT CALLBACK BoltWndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    WindowVal *w = NULL;
    for (int i = 0; i < g_nActiveWindows; i++) if (g_activeWindows[i]->hwnd == hwnd) w = g_activeWindows[i];
    switch (msg) {
        case WM_CLOSE: if (w) w->open = false; DestroyWindow(hwnd); return 0;
        case WM_DESTROY: return 0;
        case WM_MOUSEMOVE: if (w) { w->mouseX = LOWORD(lp); w->mouseY = HIWORD(lp); } return 0;
        case WM_LBUTTONDOWN: if (w) w->mouseLeft = true; return 0;
        case WM_LBUTTONUP: if (w) w->mouseLeft = false; return 0;
        case WM_RBUTTONDOWN: if (w) w->mouseRight = true; return 0;
        case WM_RBUTTONUP: if (w) w->mouseRight = false; return 0;
        case WM_PAINT: {
            PAINTSTRUCT ps; HDC hdc = BeginPaint(hwnd, &ps);
            if (w) BitBlt(hdc, 0, 0, w->w, w->h, w->memDC, 0, 0, SRCCOPY);
            EndPaint(hwnd, &ps);
            return 0;
        }
    }
    return DefWindowProc(hwnd, msg, wp, lp);
}

static COLORREF parse_color(const char *s) {
    if (s[0] == '#') {
        unsigned int r, g, b;
        sscanf(s + 1, "%02x%02x%02x", &r, &g, &b);
        return RGB(r, g, b);
    }
    return RGB(0, 0, 0);
}

static bool g_wndClassReady = false;

static Value *bolt_window(Value **args, int nargs) {
    int w = (int)args[0]->as.n, h = (int)args[1]->as.n;
    const char *title = nargs > 2 ? args[2]->as.s : "Bolt";
    if (!g_wndClassReady) {
        WNDCLASSA wc = {0};
        wc.lpfnWndProc = BoltWndProc;
        wc.hInstance = GetModuleHandle(NULL);
        wc.lpszClassName = "BoltNativeWindow";
        wc.hCursor = LoadCursor(NULL, IDC_ARROW);
        wc.hbrBackground = (HBRUSH)(COLOR_WINDOW+1);
        RegisterClassA(&wc);
        g_wndClassReady = true;
    }
    RECT r = {0, 0, w, h};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW & ~WS_THICKFRAME & ~WS_MAXIMIZEBOX, FALSE);
    HWND hwnd = CreateWindowA("BoltNativeWindow", title, WS_OVERLAPPEDWINDOW & ~WS_THICKFRAME & ~WS_MAXIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top, NULL, NULL, GetModuleHandle(NULL), NULL);
    WindowVal *win = calloc(1, sizeof(WindowVal));
    win->hwnd = hwnd; win->w = w; win->h = h; win->open = true;
    HDC hdc = GetDC(hwnd);
    win->memDC = CreateCompatibleDC(hdc);
    win->bmp = CreateCompatibleBitmap(hdc, w, h);
    SelectObject(win->memDC, win->bmp);
    ReleaseDC(hwnd, hdc);
    RECT full = {0, 0, w, h};
    FillRect(win->memDC, &full, (HBRUSH)GetStockObject(WHITE_BRUSH));
    QueryPerformanceFrequency(&win->qpcFreq);
    QueryPerformanceCounter(&win->lastTick);
    g_activeWindows[g_nActiveWindows++] = win;
    ShowWindow(hwnd, SW_SHOW);
    Value *v = malloc(sizeof(Value)); v->type = V_WINDOW; v->as.win = win;
    return v;
}

static Value *bolt_tick(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    int fps = nargs > 1 ? (int)args[1]->as.n : 60;
    if (!win->open) return mk_bool(false);
    InvalidateRect(win->hwnd, NULL, FALSE);
    MSG msg;
    while (PeekMessage(&msg, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessage(&msg); }
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    double elapsed = (double)(now.QuadPart - win->lastTick.QuadPart) / win->qpcFreq.QuadPart;
    double target = 1.0 / (fps > 0 ? fps : 60);
    if (elapsed < target) Sleep((DWORD)((target - elapsed) * 1000));
    QueryPerformanceCounter(&win->lastTick);
    return mk_bool(win->open);
}

static Value *bolt_clear(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    COLORREF c = nargs > 1 ? parse_color(args[1]->as.s) : RGB(255,255,255);
    RECT r = {0, 0, win->w, win->h};
    HBRUSH br = CreateSolidBrush(c);
    FillRect(win->memDC, &r, br);
    DeleteObject(br);
    return mk_nil();
}

static Value *bolt_rect(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    int x = (int)args[1]->as.n, y = (int)args[2]->as.n, w = (int)args[3]->as.n, h = (int)args[4]->as.n;
    COLORREF c = nargs > 5 ? parse_color(args[5]->as.s) : RGB(0,0,0);
    HBRUSH br = CreateSolidBrush(c);
    RECT r = {x, y, x+w, y+h};
    FillRect(win->memDC, &r, br);
    DeleteObject(br);
    return mk_nil();
}

static Value *bolt_circle(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    int x = (int)args[1]->as.n, y = (int)args[2]->as.n, rad = (int)args[3]->as.n;
    COLORREF c = nargs > 4 ? parse_color(args[4]->as.s) : RGB(0,0,0);
    HBRUSH br = CreateSolidBrush(c);
    HGDIOBJ old = SelectObject(win->memDC, br);
    HGDIOBJ oldPen = SelectObject(win->memDC, GetStockObject(NULL_PEN));
    Ellipse(win->memDC, x-rad, y-rad, x+rad, y+rad);
    SelectObject(win->memDC, old); SelectObject(win->memDC, oldPen);
    DeleteObject(br);
    return mk_nil();
}

static Value *bolt_line(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    int x1=(int)args[1]->as.n, y1=(int)args[2]->as.n, x2=(int)args[3]->as.n, y2=(int)args[4]->as.n;
    COLORREF c = nargs > 5 ? parse_color(args[5]->as.s) : RGB(0,0,0);
    int width = nargs > 6 ? (int)args[6]->as.n : 1;
    HPEN pen = CreatePen(PS_SOLID, width, c);
    HGDIOBJ old = SelectObject(win->memDC, pen);
    MoveToEx(win->memDC, x1, y1, NULL);
    LineTo(win->memDC, x2, y2);
    SelectObject(win->memDC, old);
    DeleteObject(pen);
    return mk_nil();
}

static Value *bolt_draw_text(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    const char *text = args[1]->as.s;
    int x = (int)args[2]->as.n, y = (int)args[3]->as.n;
    COLORREF c = nargs > 4 ? parse_color(args[4]->as.s) : RGB(0,0,0);
    SetTextColor(win->memDC, c);
    SetBkMode(win->memDC, TRANSPARENT);
    TextOutA(win->memDC, x, y, text, (int)strlen(text));
    return mk_nil();
}

static int vk_for_key(const char *name) {
    if (strcmp(name, "left") == 0) return VK_LEFT;
    if (strcmp(name, "right") == 0) return VK_RIGHT;
    if (strcmp(name, "up") == 0) return VK_UP;
    if (strcmp(name, "down") == 0) return VK_DOWN;
    if (strcmp(name, "space") == 0) return VK_SPACE;
    if (strcmp(name, "escape") == 0) return VK_ESCAPE;
    if (strlen(name) == 1) return toupper((unsigned char)name[0]);
    return 0;
}

static Value *bolt_key(Value **args, int nargs) {
    (void)args[0];
    int vk = vk_for_key(args[1]->as.s);
    if (!vk) return mk_bool(false);
    return mk_bool((GetAsyncKeyState(vk) & 0x8000) != 0);
}

static Value *bolt_mouse_x(Value **args, int nargs) { return mk_num(args[0]->as.win->mouseX); }
static Value *bolt_mouse_y(Value **args, int nargs) { return mk_num(args[0]->as.win->mouseY); }
static Value *bolt_mouse_down(Value **args, int nargs) {
    WindowVal *win = args[0]->as.win;
    const char *btn = nargs > 1 ? args[1]->as.s : "left";
    return mk_bool(strcmp(btn, "right") == 0 ? win->mouseRight : win->mouseLeft);
}
static Value *bolt_close_window(Value **args, int nargs) { args[0]->as.win->open = false; return mk_nil(); }
static Value *bolt_beep(Value **args, int nargs) {
    int freq = (int)args[0]->as.n;
    int ms = nargs > 1 ? (int)args[1]->as.n : 200;
    if (freq < 37) freq = 37; if (freq > 32767) freq = 32767;
    Beep(freq, ms);
    return mk_nil();
}
static Value *bolt_rects_overlap(Value **args, int nargs) {
    double ax=args[0]->as.n, ay=args[1]->as.n, aw=args[2]->as.n, ah=args[3]->as.n;
    double bx=args[4]->as.n, by=args[5]->as.n, bw=args[6]->as.n, bh=args[7]->as.n;
    bool overlap = ax < bx+bw && ax+aw > bx && ay < by+bh && ay+ah > by;
    return mk_bool(overlap);
}
#endif

/* ============================ Core builtins ============================ */

static Value *native_call(Env *env, const char *name, Expr **argExprs, int nargs) {
    Value **args = malloc(sizeof(Value*) * (nargs ? nargs : 1));
    for (int i = 0; i < nargs; i++) args[i] = eval(argExprs[i], env);
    Value *result = NULL;

    if (strcmp(name, "print") == 0) {
        for (int i = 0; i < nargs; i++) { if (i) printf(" "); value_print(args[i], stdout); }
        printf("\n");
        result = mk_nil();
    } else if (strcmp(name, "len") == 0) {
        Value *v = args[0];
        result = mk_num(v->type == V_LIST ? v->as.list.len : v->type == V_STR ? (double)strlen(v->as.s) : v->type == V_MAP ? v->as.map.len : 0);
    } else if (strcmp(name, "type") == 0) {
        const char *t = "nil";
        switch (args[0]->type) {
            case V_NUM: t = "number"; break; case V_STR: t = "string"; break;
            case V_BOOL: t = "bool"; break; case V_LIST: t = "list"; break;
            case V_MAP: t = "map"; break; case V_FUNC: t = "function"; break;
            default: break;
        }
        result = mk_str(t);
    } else if (strcmp(name, "range") == 0) {
        double start = 0, end, step = 1;
        if (nargs == 1) end = args[0]->as.n;
        else { start = args[0]->as.n; end = args[1]->as.n; if (nargs > 2) step = args[2]->as.n; }
        Value *l = mk_list();
        for (double i = start; step > 0 ? i < end : i > end; i += step) list_push(l, mk_num(i));
        result = l;
    } else if (strcmp(name, "push") == 0) { list_push(args[0], args[1]); result = args[0]; }
    else if (strcmp(name, "pop") == 0) { Value *v = args[0]; result = v->as.list.len ? v->as.list.items[--v->as.list.len] : mk_nil(); }
    else if (strcmp(name, "keys") == 0) {
        Value *l = mk_list();
        for (int i = 0; i < args[0]->as.map.len; i++) list_push(l, mk_str(args[0]->as.map.entries[i].key));
        result = l;
    } else if (strcmp(name, "str") == 0) {
        Value *v = args[0];
        result = v->type == V_STR ? v : v->type == V_NUM ? mk_str(num_to_str(v->as.n)) : mk_str(v->type == V_BOOL ? (v->as.b?"true":"false") : "nil");
    } else if (strcmp(name, "num") == 0) {
        Value *v = args[0];
        result = v->type == V_NUM ? v : mk_num(v->type == V_STR ? atof(v->as.s) : 0);
    } else if (strcmp(name, "upper") == 0) {
        char *s = strdup(args[0]->as.s); for (char *c = s; *c; c++) *c = toupper((unsigned char)*c);
        result = mk_str(s); free(s);
    } else if (strcmp(name, "lower") == 0) {
        char *s = strdup(args[0]->as.s); for (char *c = s; *c; c++) *c = tolower((unsigned char)*c);
        result = mk_str(s); free(s);
    } else if (strcmp(name, "trim") == 0) {
        const char *s = args[0]->as.s; while (isspace((unsigned char)*s)) s++;
        char *buf = strdup(s); int n = (int)strlen(buf);
        while (n > 0 && isspace((unsigned char)buf[n-1])) buf[--n] = 0;
        result = mk_str(buf); free(buf);
    } else if (strcmp(name, "sqrt") == 0) result = mk_num(sqrt(args[0]->as.n));
    else if (strcmp(name, "abs") == 0) result = mk_num(fabs(args[0]->as.n));
    else if (strcmp(name, "floor") == 0) result = mk_num(floor(args[0]->as.n));
    else if (strcmp(name, "ceil") == 0) result = mk_num(ceil(args[0]->as.n));
    else if (strcmp(name, "min") == 0 || strcmp(name, "max") == 0) {
        bool want_max = strcmp(name, "max") == 0;
        double best; bool have = false;
        if (nargs == 1 && args[0]->type == V_LIST) {
            for (int i = 0; i < args[0]->as.list.len; i++) {
                double v = args[0]->as.list.items[i]->as.n;
                if (!have || (want_max ? v > best : v < best)) { best = v; have = true; }
            }
        } else {
            for (int i = 0; i < nargs; i++) {
                double v = args[i]->as.n;
                if (!have || (want_max ? v > best : v < best)) { best = v; have = true; }
            }
        }
        result = mk_num(have ? best : 0);
    }
#ifdef _WIN32
    else if (strcmp(name, "window") == 0) result = bolt_window(args, nargs);
    else if (strcmp(name, "tick") == 0) result = bolt_tick(args, nargs);
    else if (strcmp(name, "clear") == 0) result = bolt_clear(args, nargs);
    else if (strcmp(name, "rect") == 0) result = bolt_rect(args, nargs);
    else if (strcmp(name, "circle") == 0) result = bolt_circle(args, nargs);
    else if (strcmp(name, "line") == 0) result = bolt_line(args, nargs);
    else if (strcmp(name, "draw_text") == 0) result = bolt_draw_text(args, nargs);
    else if (strcmp(name, "key") == 0) result = bolt_key(args, nargs);
    else if (strcmp(name, "mouse_x") == 0) result = bolt_mouse_x(args, nargs);
    else if (strcmp(name, "mouse_y") == 0) result = bolt_mouse_y(args, nargs);
    else if (strcmp(name, "mouse_down") == 0) result = bolt_mouse_down(args, nargs);
    else if (strcmp(name, "close_window") == 0) result = bolt_close_window(args, nargs);
    else if (strcmp(name, "beep") == 0) result = bolt_beep(args, nargs);
    else if (strcmp(name, "rects_overlap") == 0) result = bolt_rects_overlap(args, nargs);
#endif

    free(args);
    return result;
}

/* ================================ Main ================================ */

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: nboltc script.bo\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "bolt: cannot open %s\n", argv[1]); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    char *src = malloc(sz + 1); fread(src, 1, sz, f); src[sz] = 0; fclose(f);

    Lexer lx = { src, 0, (int)sz, 1, NULL, 0, 0 };
    lex(&lx);
    Parser p = { lx.toks, 0 };
    int nprog;
    Stmt **prog = parse_program(&p, &nprog);

    Env *global = env_new(NULL);
    exec_block(prog, nprog, global);
    return 0;
}
