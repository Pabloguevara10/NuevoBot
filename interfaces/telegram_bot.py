def _ejecutar_panico(self, chat_id):
        """Cierra todas las posiciones registradas y cancela órdenes."""
        self._send_msg(chat_id, "🚨 EJECUTANDO PÁNICO...")
        
        count = 0
        # CORRECCIÓN: Usar list() para crear una copia estática de las llaves
        # Esto evita el error "dictionary changed size during iteration"
        ids_activos = list(self.comp.positions.keys())
        
        for pid in ids_activos:
            if pid in self.comp.positions:
                record = self.comp.positions[pid]
                plan = record['data']
                
                # Cierre a mercado
                close_side = 'SELL' if plan['side'] == 'LONG' else 'BUY'
                # Usamos place_market_order directamente a través de la conexión del OM
                self.om.conn.place_market_order(close_side, plan['side'], plan['qty'], reduce_only=True)
                
                # Borrar de memoria
                del self.comp.positions[pid]
                count += 1
            
        self.comp._guardar_estado() # Actualizar JSON vacío
        self.om.cancelar_todo() # Borrar SLs y TPs pendientes en Binance
        
        self._send_msg(chat_id, f"✅ Pánico completado. {count} posiciones cerradas.")