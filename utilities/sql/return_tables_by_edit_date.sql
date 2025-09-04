/*
Purpose: Query enterprise geodatabase feature classes for create/modify dates etc.

Instructions:
     1. Replace placeholder values in "USE" and "WHERE" clauses - see inline comments
     2. Run in SQL Server, DBeaver, or other SQL client

Usage Notes:
     Uses SQL Server syntax.

     Should be used only to compare relative date differences between tables 
     returned by the query, as 'create_date' and 'modify_date' are overwritten 
     by certain system changes, potentially leading to inaccurate results.


Reference: https://www.mytecbits.com/microsoft/sql-server/sql-server-find-table-creation-date
*/


USE DATABASENAME                   -- Use actual db name, e.g. GISPROD

SELECT
     name
	, object_id
	, create_date
	, modify_date 
	, type_desc
FROM
     sys.tables 
WHERE
     name like '%PARTIAL_STRING%'  -- Use actual query string, e.g. '%dof%'
ORDER BY
     sys.tables.modify_date DESC;
