/* gs_13 - PROC REG regression analysis */
PROC SORT DATA=work.housing;
    BY neighborhood;
RUN;

PROC REG DATA=work.housing PLOTS=NONE;
    MODEL sale_price = sqft bedrooms bathrooms lot_size year_built / VIF;
    OUTPUT OUT=work.housing_pred P=predicted R=residual;
    TITLE 'Housing Price Regression';
RUN;
QUIT;

PROC UNIVARIATE DATA=work.housing_pred NORMAL;
    VAR residual;
    HISTOGRAM residual / NORMAL;
RUN;
