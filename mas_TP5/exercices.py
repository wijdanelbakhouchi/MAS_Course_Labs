"""
TP Bonus : Système de Livraison avec SPADE
À COMPLÉTER

Prérequis:
    pip install spade
    
Exécution:
    python main.py
"""

import spade
import asyncio
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from ast import literal_eval # To safely convert string "(3,4)" to tuple

# Pour éviter les warning logs
import logging

# Baisser le niveau de verbosité
logging.getLogger("spade").setLevel(logging.CRITICAL)
logging.getLogger("pyjabber").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


# =============================================================================
# PARTIE 1 : Agent Livreur
# =============================================================================

class LivreurAgent(Agent):
    """
    Agent livreur qui répond aux appels d'offres.
    """
    
    def __init__(self, jid, password, tarif, position, disponible=True):
        super().__init__(jid, password)
        self.tarif = tarif
        self.position = position
        self.disponible = disponible
    
    def calculer_distance(self, destination):
        """Distance Manhattan vers la destination."""
        return abs(self.position[0] - destination[0]) + abs(self.position[1] - destination[1])
    
    class RecevoirCFP(CyclicBehaviour):
        """Comportement pour recevoir et traiter les CFP."""
        
        async def run(self):
            msg = await self.receive(timeout=5)
            if msg:
                performative = msg.get_metadata("performative")
                
                if performative == "cfp":
                    # Extraire la destination du msg.body "livraison:(3,4)"
                    try:
                        content = msg.body.split(":") # ["livraison", "(3,4)"]
                        destination = literal_eval(content[1]) # Convert string "(3,4)" to tuple
                        
                        print(f"  🤔 {self.agent.jid} a reçu un appel d'offre pour {destination}")

                        if self.agent.disponible:
                            # Calculer le coût (distance * tarif)
                            dist = self.agent.calculer_distance(destination)
                            cout = dist * self.agent.tarif
                            
                            # Envoyer un message "propose"
                            reply = msg.make_reply()
                            reply.set_metadata("performative", "propose")
                            reply.body = f"cout:{cout}"
                            await self.send(reply)
                            print(f"  Types: ➡️ {self.agent.jid} propose un coût de {cout}")
                        else:
                            # Envoyer un message "refuse"
                            reply = msg.make_reply()
                            reply.set_metadata("performative", "refuse")
                            reply.body = "Indisponible"
                            await self.send(reply)
                            print(f"  ⛔ {self.agent.jid} refuse (indisponible)")
                            
                    except Exception as e:
                        print(f"Erreur de lecture du message: {e}")
                
                elif performative == "accept-proposal":
                    print(f"  🎉 {self.agent.jid}: Livraison acceptée! J'y vais.")
                    # Envoyer un message "inform" avec body = "done"
                    reply = msg.make_reply()
                    reply.set_metadata("performative", "inform")
                    reply.body = "done"
                    await self.send(reply)
                
                elif performative == "reject-proposal":
                    print(f"  😞 {self.agent.jid}: Offre refusée.")
    
    async def setup(self):
        print(f"🚚 {self.jid} démarré (tarif={self.tarif}, position={self.position})")
        self.add_behaviour(self.RecevoirCFP())


# =============================================================================
# PARTIE 2 : Agent Gestionnaire
# =============================================================================

class GestionnaireAgent(Agent):
    """
    Agent gestionnaire qui coordonne les livraisons via Contract Net.
    """
    
    def __init__(self, jid, password, livreurs_jids):
        super().__init__(jid, password)
        self.livreurs_jids = livreurs_jids  # Liste des JIDs des livreurs
        self.propositions = []
        self.destination = None
    
    class LancerAppelOffres(OneShotBehaviour):
        """Comportement pour lancer un appel d'offres."""
        
        async def on_start(self):
            self.agent.propositions = []
        
        async def run(self):
            destination = self.agent.destination
            print(f"\n📢 Lancement appel d'offres pour livraison à {destination}")
            
            # Pour chaque livreur, envoyer un CFP
            for livreur_jid in self.agent.livreurs_jids:
                msg = Message(to=livreur_jid)
                msg.set_metadata("performative", "cfp")
                msg.body = f"livraison:{destination}"
                await self.send(msg)
            
            # Attendre les réponses (le CyclicBehaviour CollecterPropositions s'en charge)
            await asyncio.sleep(2)
    
    class CollecterPropositions(CyclicBehaviour):
        """Comportement pour collecter les propositions."""
        
        async def run(self):
            msg = await self.receive(timeout=3)
            if msg:
                performative = msg.get_metadata("performative")
                sender = str(msg.sender)
                
                if performative == "propose":
                    # Extraire le coût du msg.body (format: "cout:XX")
                    try:
                        cout_str = msg.body.split(":")[1]
                        cout = float(cout_str)
                        
                        # Ajouter à self.agent.propositions
                        self.agent.propositions.append({'livreur': sender, 'cout': cout})
                        print(f"  📥 Proposition reçue de {sender}: {cout}")
                    except ValueError:
                        print(f"Erreur format cout de {sender}")
                
                elif performative == "refuse":
                    print(f"  ❌ {sender} a refusé")
                
                elif performative == "inform":
                    if msg.body == "done":
                        print(f"  ✅ CONFIRMATION: Livraison terminée par {sender}")
    
    class SelectionnerMeilleur(OneShotBehaviour):
        """Comportement pour sélectionner la meilleure offre."""
        
        async def run(self):
            await asyncio.sleep(3)  # Attendre que les propositions arrivent
            
            print(f"\n🔍 Évaluation des {len(self.agent.propositions)} propositions...")
            
            if not self.agent.propositions:
                print("  Aucune proposition reçue! Abandon de la mission.")
                return
            
            # Trouver la proposition avec le coût minimum
            meilleure_offre = min(self.agent.propositions, key=lambda x: x['cout'])
            gagnant_jid = meilleure_offre['livreur']
            print(f"  ⭐ Le gagnant est {gagnant_jid} avec un coût de {meilleure_offre['cout']}")
            
            # Répondre à tous les livreurs
            for prop in self.agent.propositions:
                livreur = prop['livreur']
                msg = Message(to=livreur)
                
                if livreur == gagnant_jid:
                    msg.set_metadata("performative", "accept-proposal")
                    msg.body = "Tu as le job"
                else:
                    msg.set_metadata("performative", "reject-proposal")
                    msg.body = "Trop cher"
                
                await self.send(msg)
    
    async def setup(self):
        print(f"📋 {self.jid} démarré")
        self.add_behaviour(self.CollecterPropositions())
    
    def lancer_livraison(self, destination):
        """Lancer une livraison vers une destination."""
        self.destination = destination
        self.add_behaviour(self.LancerAppelOffres())
        self.add_behaviour(self.SelectionnerMeilleur())


# =============================================================================
# PARTIE 3 : Fonction principale
# =============================================================================

async def main():
    """Lancer la simulation."""
    print("=" * 60)
    print("🚚 SIMULATION SYSTÈME DE LIVRAISON SPADE")
    print("=" * 60)
    
    # Création des 3 agents livreurs selon l'énoncé
    livreur_a = LivreurAgent("livreur_a@localhost", "password", tarif=2.0, position=(0,0), disponible=True)
    livreur_b = LivreurAgent("livreur_b@localhost", "password", tarif=1.5, position=(5,5), disponible=True)
    livreur_c = LivreurAgent("livreur_c@localhost", "password", tarif=1.0, position=(10,0), disponible=False)
    
    livreurs = [livreur_a, livreur_b, livreur_c]
    
    # Création du gestionnaire
    gestionnaire = GestionnaireAgent("gestionnaire@localhost", "password", ["livreur_a@localhost", "livreur_b@localhost", "livreur_c@localhost"])
    
    # Démarrage des agents
    await livreur_a.start()
    await livreur_b.start()
    await livreur_c.start()
    await gestionnaire.start()
    
    # Attendre que les agents soient prêts
    await asyncio.sleep(2)
    
    # Lancer une livraison vers (3, 4)
    gestionnaire.lancer_livraison((3, 4))
    
    # Attendre la fin de la simulation
    print("\n⏳ Simulation en cours (10s)...")
    await asyncio.sleep(10)
    
    # Arrêt des agents
    print("\n🛑 Arrêt des agents...")
    await livreur_a.stop()
    await livreur_b.stop()
    await livreur_c.stop()
    await gestionnaire.stop()
    
    print("\n" + "=" * 60)
    print("✅ SIMULATION TERMINÉE")
    print("=" * 60)

if __name__ == "__main__":
    # embedded_xmpp_server=True lance automatiquement le serveur XMPP
    spade.run(main(), embedded_xmpp_server=True)
