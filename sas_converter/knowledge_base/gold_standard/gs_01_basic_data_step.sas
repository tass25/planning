/* gs_01 - Basic DATA step with variable assignments */
OPTIONS MPRINT SYMBOLGEN;

DATA work.employees;
    SET sashelp.class;
    LENGTH full_name $50;
    full_name = CATX(' ', name, 'Employee');
    age_group = IFC(age >= 14, 'Senior', 'Junior');
    bmi = weight / (height**2) * 703;
    KEEP name full_name age age_group bmi;
RUN;
