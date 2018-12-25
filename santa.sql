CREATE TABLE IF NOT EXISTS "recipients" (
"server_id" TEXT,
"recipient_id" TEXT,
"wish" TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS "recipient_index" ON "recipients" ("server_id","recipient_id");


CREATE TABLE IF NOT EXISTS "senders" (
"server_id" TEXT,
"sender_id" TEXT,
"recipient_id" TEXT,
"gift" TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS "sender_index" ON "senders" ("server_id","sender_id");


CREATE TABLE IF NOT EXISTS "servers" (
"server_id" TEXT PRIMARY KEY,
"state" TEXT,
"budget" TEXT
);
