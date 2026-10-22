package com.freecoltv.app

import android.app.Application

/**
 * Punto de entrada de la app. En el MVP no inicializa nada pesado;
 * el graph de datos se construye en [DataGraph].
 */
class FreeColTvApp : Application()
