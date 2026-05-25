%*** SPORT TOURNAMENT SCHEDULING (OPPONENT MODEL) ***

%------------------ parameters ----------------------
int: n;                         % number of teams (even)
set of int: TEAM   = 1..n;
set of int: WEEK   = 1..(n-1);
set of int: PERIOD = 1..(n div 2);

constraint n mod 2 = 0;

%------------------ variables -----------------------

% opponent[t,w] = team that t plays against in week w
array[TEAM, WEEK] of var TEAM: opp;

% home[t,w] = true if team t plays at home in week w
array[TEAM, WEEK] of var bool: home;

% period[t,w] = period in which team t plays in week w
array[TEAM, WEEK] of var PERIOD: period;

%------------------ core constraints ----------------

% no team plays itself
constraint forall(t in TEAM, w in WEEK)(
  opp[t,w] != t
);

% matches are symmetric
constraint forall(t in TEAM, w in WEEK)(
  opp[opp[t,w], w] = t
);

% every team pair meets exactly once
constraint forall(t1, t2 in TEAM where t1 < t2)(
  sum(w in WEEK)(bool2int(opp[t1,w] == t2)) = 1
);

%------------------ home / away ---------------------

% exactly one home team per match
constraint forall(t in TEAM, w in WEEK)(
  home[t,w] != home[opp[t,w], w]
);

%------------------ periods -------------------------

% teams in a match share the same period
constraint forall(t in TEAM, w in WEEK)(
  period[t,w] = period[opp[t,w], w]
);

% exactly one match per period per week
constraint forall(p in PERIOD, w in WEEK)(
  sum(t in TEAM)(bool2int(period[t,w] = p)) = 2
);

% optional: limit how often a team uses the same period
constraint forall(t in TEAM, p in PERIOD)(
  sum(w in WEEK)(bool2int(period[t,w] = p)) <= 2
);

%------------------ symmetry breaking ----------------

% fix first week pairings
constraint forall(p in PERIOD)(
  opp[2*p-1,1] = 2*p /\
  opp[2*p,1]   = 2*p-1
);

% fix home/away for first week
constraint forall(p in PERIOD)(
  home[2*p-1,1] = true /\
  home[2*p,1]   = false
);

constraint forall(p in PERIOD)(
  period[2*p-1, 1] = p /\
  period[2*p,   1] = p
);


constraint forall(w in 1..(n-2)) (
    opp[1,w] < opp[1,w+1]
);

%------------------ objective -----------------------

array[TEAM] of var int: home_count;
constraint forall(t in TEAM)(
  home_count[t] = sum(w in WEEK)(bool2int(home[t,w]))
);

var int: balance =
  max(t in TEAM)(
    max(2*home_count[t]-(n-1), (n-1)-2*home_count[t])
  );

solve minimize balance;
int: balance_lb = (n-1) mod 2;   % = 1 when n is even, = 0 when n is odd

%------------------ output --------------------------

output
["\nn: " ++ show(n) ++ "\n"] ++
[
  "\nsol: "
] ++
[
  "[" ++
  concat([
    let {
      array[int] of int: ht = [t | t in TEAM
                              where fix(period[t,w]) = p /\ fix(home[t,w]) = true],
      array[int] of int: at = [t | t in TEAM
                              where fix(period[t,w]) = p /\ fix(home[t,w]) = false]
    } in
    if length(ht)=1 /\ length(at)=1 then
      "[" ++ show(ht[1]) ++ "," ++ show(at[1]) ++ "]"
    else
      ""
    endif
  | w in WEEK]) ++ "]" ++
  (if p < max(PERIOD) then "," else "" endif) ++ "\n"
| p in PERIOD
] ++
[
  "\nopt: " ++ (if fix(balance) = balance_lb then "true" else "false" endif) ++ "\n",
  "\nobj: ", show(balance), "\n"
];
