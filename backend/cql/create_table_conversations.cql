CREATE TABLE chatbot.conversations (
   user_id bigint,
   conversation_id timeuuid, 
   title text, 
   PRIMARY KEY (user_id, conversation_id)) 
WITH CLUSTERING ORDER BY (conversation_id DESC);