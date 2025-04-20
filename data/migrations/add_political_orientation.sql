ALTER TABLE articles
ADD COLUMN political_orientation VARCHAR(20),
ADD COLUMN political_confidence FLOAT,
ADD COLUMN political_reasoning TEXT,
ADD COLUMN source_orientation JSONB DEFAULT '{
    "left_percent": 0,
    "center_left_percent": 0,
    "neutral_percent": 100,
    "center_right_percent": 0,
    "right_percent": 0
}'::jsonb;