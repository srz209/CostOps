CREATE OR REPLACE PROCEDURE COSTOPS_APP.LOG_RECOMMENDATION_EVENT(
    P_RECOMMENDATION_ID STRING,
    P_EVENT_TYPE STRING,
    P_ACTOR STRING,
    P_DETAILS STRING,
    P_PREVIOUS_STATUS STRING,
    P_NEW_STATUS STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    INSERT INTO COSTOPS_APP.RECOMMENDATION_EVENT_LOG (
        event_id,
        recommendation_id,
        event_ts,
        event_type,
        actor,
        details,
        previous_status,
        new_status
    )
    VALUES (
        UUID_STRING(),
        P_RECOMMENDATION_ID,
        CURRENT_TIMESTAMP(),
        P_EVENT_TYPE,
        P_ACTOR,
        P_DETAILS,
        P_PREVIOUS_STATUS,
        P_NEW_STATUS
    );

    RETURN 'EVENT_LOGGED';
END;
$$;

CREATE OR REPLACE PROCEDURE COSTOPS_APP.UPDATE_RECOMMENDATION_STATUS(
    P_RECOMMENDATION_ID STRING,
    P_NEW_STATUS STRING,
    P_ACTOR STRING,
    P_DETAILS STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    V_PREVIOUS_STATUS STRING;
    V_EVENT_TYPE STRING;
    V_DETAILS STRING;
BEGIN
    SELECT recommendation_status
      INTO :V_PREVIOUS_STATUS
      FROM COSTOPS_APP.COST_RECOMMENDATION
     WHERE recommendation_id = P_RECOMMENDATION_ID;

    V_EVENT_TYPE := CASE P_NEW_STATUS
        WHEN 'Selected' THEN 'SELECTED'
        WHEN 'Accepted' THEN 'ACCEPTED'
        WHEN 'Deferred' THEN 'DEFERRED'
        WHEN 'Rejected' THEN 'REJECTED'
        WHEN 'Implemented' THEN 'IMPLEMENTED'
        WHEN 'Realized' THEN 'SAVINGS_REALIZED'
        ELSE 'STATUS_CHANGED'
    END;

    V_DETAILS := COALESCE(NULLIF(P_DETAILS, ''), 'Recommendation status updated.');

    UPDATE COSTOPS_APP.COST_RECOMMENDATION
       SET recommendation_status = P_NEW_STATUS,
           last_seen_at = CURRENT_TIMESTAMP(),
           accepted_at = CASE
               WHEN P_NEW_STATUS IN ('Accepted', 'Implemented', 'Realized')
                    AND accepted_at IS NULL THEN CURRENT_TIMESTAMP()
               ELSE accepted_at
           END,
           implemented_at = CASE
               WHEN P_NEW_STATUS IN ('Implemented', 'Realized') THEN CURRENT_TIMESTAMP()
               ELSE implemented_at
           END,
           realized_at = CASE
               WHEN P_NEW_STATUS = 'Realized' THEN CURRENT_TIMESTAMP()
               ELSE realized_at
           END,
           updated_at = CURRENT_TIMESTAMP()
     WHERE recommendation_id = P_RECOMMENDATION_ID;

    CALL COSTOPS_APP.LOG_RECOMMENDATION_EVENT(
        P_RECOMMENDATION_ID,
        V_EVENT_TYPE,
        P_ACTOR,
        V_DETAILS,
        V_PREVIOUS_STATUS,
        P_NEW_STATUS
    );

    RETURN 'STATUS_UPDATED';
END;
$$;

CREATE OR REPLACE PROCEDURE COSTOPS_APP.LOG_SQL_COPIED(
    P_RECOMMENDATION_ID STRING,
    P_ACTOR STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    V_CURRENT_STATUS STRING;
BEGIN
    SELECT recommendation_status
      INTO :V_CURRENT_STATUS
      FROM COSTOPS_APP.COST_RECOMMENDATION
     WHERE recommendation_id = P_RECOMMENDATION_ID;

    CALL COSTOPS_APP.LOG_RECOMMENDATION_EVENT(
        P_RECOMMENDATION_ID,
        'SQL_COPIED',
        P_ACTOR,
        'Copied generated SQL or implementation guidance from the recommendation detail.',
        V_CURRENT_STATUS,
        V_CURRENT_STATUS
    );

    RETURN 'SQL_COPY_LOGGED';
END;
$$;
