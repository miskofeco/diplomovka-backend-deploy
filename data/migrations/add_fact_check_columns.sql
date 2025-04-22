ALTER TABLE articles
ADD COLUMN IF NOT EXISTS fact_check_results JSONB DEFAULT '{"facts": [], "summary": ""}'::jsonb,
ADD COLUMN IF NOT EXISTS summary_annotations JSONB DEFAULT '{"text": "", "annotations": []}'::jsonb;