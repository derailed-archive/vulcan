# Vulcan
# Copyright (c) 2021-2022 Venera Inc. All Rights Reserved.
# Copyright (c) 2022 Gozzle Inc. All Rights Reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
import asyncio
import random
import re

import bcrypt
from fastapi import APIRouter, Request

from ..checks import authorize, verify_email
from ..database import User, to_dict
from ..errors import BadData, Forbidden
from ..snowflakes import snowflake_factory
from ..tokenize import create_token as ctoken
from ..utils import get_data, jsonify

users_router = APIRouter(prefix='/users')


USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9\-_]{1,45}$')
LOCALES = [
    'en-US',
    'en-GB',
]


@users_router.get('/@me')
async def get_me(req: Request):
    return jsonify(to_dict(authorize(req=req)))


@users_router.get('/@me/logout')
async def logout(_: Request):
    resp = jsonify({})

    try:
        resp.delete_cookie('authorization', secure=True)
    except:
        return resp
    else:
        return resp


@users_router.get('/@me/create-token')
async def create_token(req: Request):
    email = str(req.query_params.get('email'))
    password = str(req.query_params.get('password'))

    user = User.objects(User.email == email).get()

    loop = asyncio.get_running_loop()
    valid_pw = await loop.run_in_executor(
        None, bcrypt.checkpw, password.encode(), user.password.encode()
    )

    if not valid_pw:
        raise Forbidden(custom_msg='Invalid Password')

    resp = jsonify({}, 201)
    resp.set_cookie('authorization', ctoken(user.id, user.password), secure=True)

    return resp


@users_router.post('')
async def create_user(request: Request):
    data: dict = await get_data(req=request)
    loop = asyncio.get_running_loop()

    if request.cookies.get('authorization'):
        raise BadData(custom_msg='Already logged into another account.')

    name = str(data['name'])

    if len(name) > 45:
        raise BadData(custom_msg='Name length over 45')
    elif len(name) < 3:
        raise BadData(custom_msg='Name length is under 3')

    password = await loop.run_in_executor(
        None, bcrypt.hashpw, str(data['password']).encode(), bcrypt.gensalt(17)
    )
    password = password.decode()

    locale = 'en-US'

    if data.get('locale'):
        if str(data['locale']) not in LOCALES:
            raise BadData(
                'Invalid locale',
                str(data['locale']) + ' is not a valid and/or usable locale.',
            )
        else:
            locale = str(data['locale'])

    email = str(data['email'])
    verify_email(email=email)

    if len(email) > 50:
        raise BadData('Max email Length is 50', custom_msg='Invalid email length')

    TS = 0

    while True:
        discriminator = random.randint(0, 9999)
        discriminator = '%04d' % discriminator

        try:
            User.objects(
                User.name == name,
                User.discriminator == discriminator
            ).get()
        except:
            break

        if TS == 5000:
            raise BadData(custom_msg='Name is too commonly used.')

        TS += 1

    user: User = User.create(
        id=snowflake_factory.write(),
        email=email,
        password=password,
        name=name,
        locale=locale,
        discriminator=discriminator
    )

    asdict = to_dict(user)

    response = jsonify(asdict, 201)

    response.set_cookie('authorization', ctoken(user.id, user.password), secure=True)

    return response
