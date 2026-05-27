import { Tabs } from 'expo-router';
import { View, StyleSheet } from 'react-native';

export default function AppLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: '#14b8a6',
        tabBarInactiveTintColor: '#64748b',
        tabBarLabelStyle: styles.tabLabel,
      }}
    >
      <Tabs.Screen
        name="dashboard/index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color }) => <TabIcon emoji="🏡" color={color} />,
        }}
      />
      <Tabs.Screen
        name="wizard"
        options={{
          title: 'Household Guide',
          tabBarIcon: ({ color }) => <TabIcon emoji="📋" color={color} />,
          href: '/(app)/wizard',
        }}
      />
      <Tabs.Screen
        name="hours/index"
        options={{
          title: 'Hours',
          tabBarIcon: ({ color }) => <TabIcon emoji="⏱" color={color} />,
        }}
      />
      <Tabs.Screen
        name="guide/index"
        options={{
          title: 'Guide',
          tabBarIcon: ({ color }) => <TabIcon emoji="📄" color={color} />,
        }}
      />
    </Tabs>
  );
}

function TabIcon({ emoji, color }: { emoji: string; color: string }) {
  return (
    <View style={styles.iconContainer}>
      <View style={[styles.iconDot, { opacity: color === '#14b8a6' ? 1 : 0 }]} />
      {/* In production, use vector icons — emoji here for clarity */}
    </View>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: '#ffffff',
    borderTopColor: '#e2e8f0',
    borderTopWidth: 1,
    paddingTop: 4,
  },
  tabLabel: { fontSize: 11, fontWeight: '500' },
  iconContainer: { alignItems: 'center' },
  iconDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#14b8a6', marginTop: 2 },
});
