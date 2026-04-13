CREATE KEYSPACE IF NOT EXISTS chatbot
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
AND durable_writes = true;

CREATE TABLE chatbot.conversations (
   user_id bigint,
   conversation_id timeuuid, 
   title text, 
   PRIMARY KEY (user_id, conversation_id)) 
WITH CLUSTERING ORDER BY (conversation_id DESC);

CREATE TABLE chatbot.messages (
   conversation_id timeuuid, 
   created_at timestamp,
   role text,
   content text, 
   PRIMARY KEY (conversation_id, created_at)) 
WITH CLUSTERING ORDER BY (created_at DESC);