# Time API

## Common provisions

#### Terminology

The terminology of [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt) (specifically __must__, __should__, __may__ and their negatives) applies.  The word __will__, when applied to the Service API, has the same meaning as __must__.

#### Protocol

The API supports communication over HTTP only.

## Endpoints

### Now

This endpoint can be called to check the current server time

##### Query String
 
The client __must__ submit a request to the endpoint `/now`.

##### Request

The client __must__ submit a request body with a GET method:

```
GET /now HTTP/1.1
Host: time.env.fathomai.com

```

##### Responses
 
The Service __will__ respond with HTTP Status `204 No Content`, with an empty body, and with a response header `X-Time` containing the current time in unix timestamp format:

```
HTTP/1.1 204 No Content
Server: nginx/1.15.0
Date: Tue, 12 Jun 2018 20:44:53 GMT
Connection: keep-alive
X-Time: 1528836293
```
