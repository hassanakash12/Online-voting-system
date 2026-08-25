-- Run this in phpMyAdmin's SQL tab (with ai_online_voting_system database selected)
-- This converts the old plaintext password "123456" into a proper hash
-- for both existing accounts (id=1 admin, id=6 voter) so login works
-- with the corrected app.py

UPDATE users
SET password = 'scrypt:32768:8:1$BxgTmcekvvfXfZI6$b7de5c12a9e9ec6429eb7c281c50033626ddec098560f66def2348be0e01ffc44474972def6e1cb5fe42be455923827e2549127ca6e9987750c2c57793f92cc1'
WHERE id IN (1, 6);

-- After running this, both accounts can log in using password: 123456
-- (the actual password itself is unchanged, only how it's stored)
