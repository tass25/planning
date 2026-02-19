/* gs_18 - PROC PRINT with formatting and WHERE */
PROC PRINT DATA=work.inventory NOOBS LABEL;
    WHERE quantity_on_hand < reorder_point;
    VAR product_id product_name quantity_on_hand reorder_point supplier;
    LABEL product_id = 'Product ID'
          product_name = 'Product'
          quantity_on_hand = 'Current Stock'
          reorder_point = 'Reorder At'
          supplier = 'Supplier';
    FORMAT quantity_on_hand reorder_point COMMA8.;
    TITLE 'Items Below Reorder Point';
RUN;

PROC SORT DATA=work.inventory OUT=work.inv_sorted;
    BY supplier product_name;
RUN;
