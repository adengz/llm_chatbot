CREATE TABLE chatbot.messages (
   conversation_id timeuuid, 
   created_at timestamp,
   role text,
   content text, 
   PRIMARY KEY (conversation_id, created_at)) 
WITH CLUSTERING ORDER BY (created_at DESC);