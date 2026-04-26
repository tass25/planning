data output;
    set input;
    if age > 18 then adult = 1;
    else adult = 0;
    total_income = salary + bonus;
run;
