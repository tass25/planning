/* gs_09 - DATA step with INPUT and INFILE (reading raw data) */
DATA work.survey_responses;
    INFILE '/data/raw/survey_2025.csv' DLM=',' DSD FIRSTOBS=2 MISSOVER;
    INPUT respondent_id
          age
          gender $
          satisfaction
          recommend $
          comments $200.;
    IF satisfaction < 1 OR satisfaction > 10 THEN DELETE;
    response_date = TODAY();
    FORMAT response_date DATE9.;
RUN;

DATA work.survey_coded;
    SET work.survey_responses;
    LENGTH sat_group $15;
    IF satisfaction >= 8 THEN sat_group = 'PROMOTER';
    ELSE IF satisfaction >= 6 THEN sat_group = 'PASSIVE';
    ELSE sat_group = 'DETRACTOR';
    nps_score = (satisfaction - 5) * 20;
RUN;
