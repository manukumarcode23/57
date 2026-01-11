-- Migration: Add Video Duration Constraint
-- Date: November 12, 2025
-- Description: Adds check constraint to ensure video duration is non-negative and realistic
-- BUG #23: No Validation for Video Duration

-- Add check constraint for video duration
ALTER TABLE files 
    ADD CONSTRAINT check_video_duration_valid 
    CHECK (video_duration IS NULL OR (video_duration >= 0 AND video_duration <= 86400));
