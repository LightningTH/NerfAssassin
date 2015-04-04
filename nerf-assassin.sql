drop table gameinfo;
drop table assassins;
drop table games;
drop table rules;
drop table config;

PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE gameinfo(id integer primary key, game_id integer not null, assassin_id integer not null, target_id integer, killer_id integer, kill_datetime timestamp, ranking integer, confirm_hash text, reporting_killer text);
CREATE TABLE assassins(id integer primary key, nickname text not null, firstname text, lastname text, password text, email_address text not null, picture_filename text, smack text, ranking integer, email_updates integer default 1, email_newgames integer default 1);
CREATE TABLE games(id integer primary key, start_datetime timestamp default current_timestamp, end_datetime timestamp, rule_id integer, gametype_id integer);
CREATE TABLE gametypes(id integer primary key, name text);
CREATE TABLE rules(id integer primary key, rules text, rulename text, gametype_id integer);
CREATE TABLE config(name text not null, value text, description text);
CREATE TABLE rankings(id integer primary key, assassin_id integer not null, gametype_id integer not null, ranking integer not null);
INSERT INTO config(name, value, description) values("config_password","","Password for config page");
INSERT INTO config(name, value, description) values("auto_confirm_time","120","How many minutes a person has to confirm a kill");
INSERT INTO config(name, value, description) values("from_email","","Email address to send emails from");
INSERT INTO config(name, value, description) values("email_subject","Nerf Assassin","Subject of email sent");
INSERT INTO config(name, value, description) values("email_server","","Server to connect to for sending email");
INSERT INTO config(name, value, description) values("email_server_port","587","Port of email server");
INSERT INTO config(name, value, description) values("email_username","","Username for email server (STORED PLAIN TEXT!)");
INSERT INTO config(name, value, description) values("email_password","","Password for email server (STORED PLAIN TEXT!)");
INSERT INTO config(name, value, description) values("email_usetls","0","Does server require TLS");
COMMIT;

