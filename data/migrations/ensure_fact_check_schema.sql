ALTER TABLE articles
ADD COLUMN IF NOT EXISTS fact_check_results JSONB,
ADD COLUMN IF NOT EXISTS summary_annotations JSONB;

ALTER TABLE articles
ALTER COLUMN fact_check_results TYPE JSONB
USING CASE
    WHEN fact_check_results IS NULL THEN NULL
    ELSE fact_check_results::jsonb
END,
ALTER COLUMN summary_annotations TYPE JSONB
USING CASE
    WHEN summary_annotations IS NULL THEN NULL
    ELSE summary_annotations::jsonb
END;

ALTER TABLE articles
ALTER COLUMN fact_check_results SET DEFAULT '{"status":"Neoverene fakty","facts":[]}'::jsonb,
ALTER COLUMN summary_annotations SET DEFAULT '{"text":"","annotations":[]}'::jsonb;

UPDATE articles
SET fact_check_results = CASE
    WHEN fact_check_results IS NULL THEN '{"status":"Neoverene fakty","facts":[]}'::jsonb
    WHEN jsonb_typeof(fact_check_results) <> 'object' THEN '{"status":"Neoverene fakty","facts":[]}'::jsonb
    ELSE fact_check_results
END;

UPDATE articles
SET fact_check_results = CASE
    WHEN NOT (fact_check_results ? 'facts') THEN fact_check_results || '{"facts":[]}'::jsonb
    ELSE fact_check_results
END;

UPDATE articles
SET fact_check_results = CASE
    WHEN NOT (fact_check_results ? 'status') THEN fact_check_results || '{"status":"Neoverene fakty"}'::jsonb
    ELSE fact_check_results
END;

UPDATE articles
SET summary_annotations = CASE
    WHEN summary_annotations IS NULL THEN '{"text":"","annotations":[]}'::jsonb
    WHEN jsonb_typeof(summary_annotations) <> 'object' THEN '{"text":"","annotations":[]}'::jsonb
    ELSE summary_annotations
END;

UPDATE articles
SET summary_annotations = CASE
    WHEN NOT (summary_annotations ? 'text') THEN summary_annotations || '{"text":""}'::jsonb
    ELSE summary_annotations
END;

UPDATE articles
SET summary_annotations = CASE
    WHEN NOT (summary_annotations ? 'annotations') THEN summary_annotations || '{"annotations":[]}'::jsonb
    ELSE summary_annotations
END;
