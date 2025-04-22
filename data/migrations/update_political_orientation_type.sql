ALTER TABLE articles 
ALTER COLUMN political_orientation TYPE JSONB USING political_orientation::JSONB;