UNAUTHORIZED_401 = {
    401: {
        "description": "Unauthorized – missing or invalid authentication token",
        "content": {
            "application/json": {
                "example": {"detail": "Invalid token"}
            }
        },
    }
}
